import random

from bby18.api.saves import CODE_VERSION, apply_submitted, load_session, new_session, replay
from bby18.api.saves import snapshot
from bby18.api.serialize import action_to_json, session_to_json
from bby18.api.store import SavedGame, Seat
from bby18.session import Phase

SEATS = (Seat("Me", False), Seat("You", False), Seat("Bot", True))


def _play_to_end(seed: int):
    """Play a whole game, choosing human moves at random; return the session and moves."""
    session = new_session(seed, SEATS)
    chooser = random.Random(seed)
    submitted = []
    while session.waiting_on_human():
        action = action_to_json(chooser.choice(session.legal_actions()))
        submitted.append(action)
        apply_submitted(session, action)
    return session, submitted


def test_replay_rebuilds_a_whole_game():
    session, submitted = _play_to_end(13)
    assert session.phase is Phase.GAME_OVER
    assert any(a["type"] in ("chart", "service", "upgrade") for a in submitted)
    assert session_to_json(replay(13, SEATS, submitted)) == session_to_json(session)


def test_snapshot_is_used_while_code_version_matches():
    session, submitted = _play_to_end(12)
    saved = SavedGame(
        id="g",
        owner="u",
        seed=12,
        seats=SEATS,
        actions=tuple(submitted),
        code_version=CODE_VERSION,
        snapshot=snapshot(session),
        phase=session.phase.value,
        round_label=session.game.round_label,
    )
    assert session_to_json(load_session(saved)) == session_to_json(session)
