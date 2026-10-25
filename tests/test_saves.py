import pickle
import random
import zlib

from bby18.api.saves import CODE_VERSION, apply_submitted, load_session, new_session, replay
from bby18.api.saves import snapshot
from bby18.api.serialize import MoveRecorder, action_to_json, session_to_json, tile_map
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


def _play_observed(seed: int):
    """Like ``_play_to_end``, with a fresh MoveRecorder watching each submitted action.

    Returns the session, the submitted actions, and per request the recorder and the tiles
    as they stood before it.
    """
    session = new_session(seed, SEATS)
    chooser = random.Random(seed)
    submitted, requests = [], []
    while session.waiting_on_human():
        action = action_to_json(chooser.choice(session.legal_actions()))
        submitted.append(action)
        before = tile_map(session.game)
        recorder = MoveRecorder(before)
        apply_submitted(session, action, recorder)
        requests.append((before, recorder))
    return session, submitted, requests


def test_observing_moves_does_not_change_the_game():
    observed, submitted, _ = _play_observed(13)
    unobserved, same_submitted = _play_to_end(13)
    assert submitted == same_submitted
    assert session_to_json(observed) == session_to_json(unobserved)
    assert session_to_json(replay(13, SEATS, submitted)) == session_to_json(observed)
    # The observer is never kept on the session, so saves pickle exactly as before.
    restored = pickle.loads(zlib.decompress(snapshot(observed)))
    assert session_to_json(restored) == session_to_json(observed)
    assert not any(isinstance(v, MoveRecorder) for v in vars(observed).values())


def test_dividend_frames_carry_the_revenue_being_settled():
    _, _, requests = _play_observed(13)
    frames = [f for _, recorder in requests for f in recorder.frames]
    dividends = [f for f in frames if f["action"]["type"] == "dividend"]
    assert any(f["revenue"] > 0 for f in dividends)
    for frame in dividends:
        verb = "pays" if frame["action"]["choice"] == "pay" else "withholds"
        assert frame["log"][0]["text"].startswith(f"{verb} {frame['revenue']}")
        assert frame["corporation"] == frame["log"][0]["actor"]
    assert all(f["revenue"] == 0 for f in frames if f["action"]["type"] != "dividend")


def test_frame_tiles_are_exactly_the_tiles_each_move_changed():
    session, _, requests = _play_observed(13)
    # Merging every frame's tiles, in order, onto an empty board rebuilds the board.
    merged: dict[tuple[int, int], dict] = {}
    hex_actions = 0
    for before, recorder in requests:
        assert merged == {tuple(t["hex"]): t for t in before.values()}
        for frame in recorder.frames:
            action = frame["action"]
            if action["type"] in ("chart", "upgrade", "service"):
                hex_actions += 1
                assert [t["hex"] for t in frame["after"]["tiles"]] == [action["hex"]]
            else:
                assert frame["after"]["tiles"] == []
            merged.update((tuple(t["hex"]), t) for t in frame["after"]["tiles"])
    assert hex_actions > 0
    assert merged == {tuple(t["hex"]): t for t in session_to_json(session)["tiles"]}


def test_last_frame_shows_the_state_the_request_ended_in():
    session = new_session(13, SEATS)
    chooser = random.Random(13)
    while session.waiting_on_human():
        recorder = MoveRecorder(tile_map(session.game))
        apply_submitted(session, action_to_json(chooser.choice(session.legal_actions())), recorder)
        state = session_to_json(session)
        after = recorder.frames[-1]["after"]
        for key in after.keys() - {"players", "tiles"}:
            assert after[key] == state[key], key
        assert after["players"] == [
            {k: p[k] for k in ("id", "cash", "worth", "shares", "certificates")}
            for p in state["players"]
        ]
