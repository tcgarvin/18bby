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
import pickle
import random
import zlib
from collections.abc import Iterable
from pathlib import Path

from bby18.api.serialize import Json, match_action
from bby18.api.store import Seat, SavedGame
from bby18.bots import GreedyBot
from bby18.config import DEFAULT_CONFIG
from bby18.game import Game
from bby18.network import IllegalAction
from bby18.session import Decider, GameSession


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


def new_session(seed: int, seats: Iterable[Seat]) -> GameSession:
    """A fresh game with any opening bot or forced moves already played."""
    seats = list(seats)
    rng = random.Random(seed)
    game = Game.new([s.name for s in seats], DEFAULT_CONFIG)
    bots: dict[str, Decider] = {
        player.id: GreedyBot(random.Random(rng.random()))
        for player, seat in zip(game.players, seats)
        if seat.bot
    }
    session = GameSession(game, bots, auto_forced=True)
    session.run_bots()
    return session


def apply_submitted(session: GameSession, submitted: Json) -> None:
    """Apply a client-submitted action dict. Raises ValueError or IllegalAction if not legal."""
    session.apply(match_action(session.legal_actions(), submitted))


def replay(seed: int, seats: Iterable[Seat], actions: Iterable[Json]) -> GameSession:
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
