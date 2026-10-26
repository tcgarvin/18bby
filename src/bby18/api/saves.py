"""Turning a saved game back into a live ``GameSession``, and a session into a save.

A save's durable record is its seed, seats and the actions the humans submitted. The engine is
deterministic (bots draw from generators seeded from the game seed), so replaying those actions
rebuilds the game exactly. Replaying a long game costs about a second, so each save also
carries a pickled session, trusted only while ``CODE_VERSION`` (a hash of the engine's source)
is unchanged. After a deploy that changes the engine, the first load replays and the next write
refreshes the snapshot.

If the rules changed so that a saved action is no longer legal, replay fails with
``SaveOutdated``; such a game can no longer be resumed.
"""

from __future__ import annotations

import hashlib
import os
import pickle
import random
import zlib
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from bby18.api.serialize import Json, match_action
from bby18.api.store import Seat, SavedGame
from bby18.bots import GreedyBot
from bby18.bots.roster import character_named, character_policy, draw_characters
from bby18.config import DEFAULT_CONFIG, GameConfig
from bby18.game import Game
from bby18.network import IllegalAction
from bby18.session import Decider, GameSession, MoveObserver


class SaveOutdated(Exception):
    """The saved actions no longer replay under the current rules."""


def _code_version() -> str:
    package = Path(__file__).resolve().parent.parent
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".json", ".toml", ".yaml", ".txt"}:
            digest.update(path.relative_to(package).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


CODE_VERSION = _code_version()

DEATH_STAR_RULES_ENV = "BBY18_DEATH_STAR_RULES"
"""Development switch: set to ``1`` to serve games under the experimental Death Star rules."""


def api_config() -> GameConfig:
    """The rules the API serves: ``DEFAULT_CONFIG``, or with the experimental Death Star rules
    switched on when ``BBY18_DEATH_STAR_RULES=1``. Read on every call, so the switch applies to
    games started (and saves replayed) after it changes; see docs/DEPLOYMENT.md.

    Raises ``ValueError`` for any other non-empty value, so a typo cannot quietly serve the
    wrong rules.
    """
    value = os.environ.get(DEATH_STAR_RULES_ENV, "")
    if value in ("", "0"):
        return DEFAULT_CONFIG
    if value == "1":
        return replace(DEFAULT_CONFIG, death_star_rules=True)
    raise ValueError(f"{DEATH_STAR_RULES_ENV} must be 0 or 1, not {value!r}")


def new_session(
    seed: int, seats: Iterable[Seat], observer: MoveObserver | None = None
) -> GameSession:
    """A fresh game with any opening bot or forced moves already played.

    ``observer`` sees each of those opening moves (see ``GameSession.run_bots``).
    """
    seats = list(seats)
    rng = random.Random(seed)
    game = Game.new([s.name for s in seats], api_config(), seed)
    bots: dict[str, Decider] = {
        player.id: _bot_for(seat, random.Random(rng.random()))
        for player, seat in zip(game.players, seats)
        if seat.bot
    }
    session = GameSession(game, bots, auto_forced=True)
    session.run_bots(observer)
    return session


def _bot_for(seat: Seat, rng: random.Random) -> Decider:
    """A roster character at its difficulty, or the original bot for a seat without one."""
    if not seat.difficulty:
        return GreedyBot(rng)
    return GreedyBot(rng, character_policy(character_named(seat.character), seat.difficulty))


def bot_seats(seed: int, seats: Iterable[Seat]) -> tuple[Seat, ...]:
    """``seats`` with each bot seat that has a difficulty given a character drawn from the
    seed, named after it."""
    seats = list(seats)
    wanted = [i for i, s in enumerate(seats) if s.bot and s.difficulty]
    for i, character in zip(wanted, draw_characters(seed, len(wanted))):
        seats[i] = replace(seats[i], name=character.name, character=character.name)
    return tuple(seats)


def apply_submitted(
    session: GameSession, submitted: Json, observer: MoveObserver | None = None
) -> None:
    """Apply a client-submitted action dict, and the automatic moves after it, each seen by
    ``observer`` if given. Raises ValueError or IllegalAction if not legal."""
    session.apply(match_action(session.legal_actions(), submitted), observer)


def replay(seed: int, seats: Iterable[Seat], actions: Iterable[Json]) -> GameSession:
    """Rebuild a game from its seed, seats and submitted actions. Nothing observes the moves,
    which keeps replaying a whole game fast."""
    session = new_session(seed, seats)
    for number, submitted in enumerate(actions, start=1):
        try:
            apply_submitted(session, submitted)
        except (ValueError, IllegalAction) as exc:
            raise SaveOutdated(
                f"Saved move {number} ({submitted}) is not legal under the current rules"
            ) from exc
    return session


def load_session(saved: SavedGame) -> GameSession:
    if saved.code_version == CODE_VERSION:
        session: GameSession = pickle.loads(zlib.decompress(saved.snapshot))
        return session
    return replay(saved.seed, saved.seats, saved.actions)


def snapshot(session: GameSession) -> bytes:
    return zlib.compress(pickle.dumps(session, protocol=pickle.HIGHEST_PROTOCOL))
