import pytest
from fastapi.testclient import TestClient

from bby18.api.app import create_app
from bby18.api.auth import AuthError
from bby18.api.store import MemoryStore
from bby18.config import DEFAULT_CONFIG


class HeaderUser:
    """Takes the caller's user id straight from the Authorization header, for ownership tests."""

    def user_id(self, authorization: str) -> str:
        if not authorization:
            raise AuthError("no user")
        return authorization


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def client(store):
    return TestClient(create_app(store, store, HeaderUser()), headers={"Authorization": "alice"})


def test_board_endpoint(client):
    data = client.get("/api/board").json()
    assert len(data["hexes"]) == 127
    assert len(data["planets"]) == 24


def test_rules_endpoint_matches_config(client):
    rules = client.get("/api/rules").json()
    assert rules["chartCost"] == DEFAULT_CONFIG.chart_cost
    assert rules["parPrices"] == list(DEFAULT_CONFIG.par_prices)
    assert rules["stockMarket"][0][0] == DEFAULT_CONFIG.stock_market[0][0]
    assert ["A", "M"] in rules["typedPairs"]
    assert {c["id"] for c in rules["corporations"]} == {c.id for c in DEFAULT_CONFIG.corporations}


def test_rules_endpoint_is_public(store):
    anonymous = TestClient(create_app(store, store, HeaderUser()))
    assert anonymous.get("/api/rules").status_code == 200


def test_new_game_and_act(client):
    r = client.post(
        "/api/games", json={"seats": [{"name": "Me"}, {"name": "Bot", "bot": True}], "seed": 5}
    )
    assert r.status_code == 200
    body = r.json()
    state = body["state"]
    assert state["phase"] == "stock"
    assert state["waitingOnHuman"]
    assert state["currentPlayer"] == "P1"
    start = next(a for a in state["legalActions"] if a["type"] == "buy" and a.get("par") == 60)
    r = client.post(f"/api/games/{body['gameId']}/actions", json={"action": start})
    assert r.status_code == 200
    state = r.json()
    assert state["corporations"][0]["status"] == "parred"
    assert state["currentPlayer"] == "P1"  # the bot seat already acted


def test_game_state_lists_terrain_for_its_seed(client):
    seats = [{"name": "Me"}, {"name": "Bot", "bot": True}]
    first = client.post("/api/games", json={"seats": seats, "seed": 5}).json()["state"]
    again = client.post("/api/games", json={"seats": seats, "seed": 5}).json()["state"]
    other = client.post("/api/games", json={"seats": seats, "seed": 6}).json()["state"]
    kinds = {t["kind"] for t in first["terrain"]}
    assert kinds == {"asteroid", "nebula"}
    assert first["terrain"] == again["terrain"] != other["terrain"]
    assert first["config"]["nebulaChartSurcharge"] == DEFAULT_CONFIG.nebula_chart_surcharge


def test_illegal_action_returns_400(client):
    body = client.post("/api/games", json={"seats": [{"name": "A"}, {"name": "B"}]}).json()
    r = client.post(
        f"/api/games/{body['gameId']}/actions",
        json={"action": {"type": "dividend", "choice": "pay"}},
    )
    assert r.status_code == 400
    assert client.get("/api/games/nope").status_code == 404


def test_network_action_count_advances_within_a_turn(client):
    body = client.post(
        "/api/games", json={"seats": [{"name": "A"}, {"name": "B"}], "seed": 1}
    ).json()
    game_id, state = body["gameId"], body["state"]
    while state["phase"] != "network":
        legal = state["legalActions"]
        action = next((a for a in legal if a["type"] == "buy"), None) or next(
            a for a in legal if a["type"] == "pass"
        )
        state = client.post(f"/api/games/{game_id}/actions", json={"action": action}).json()
    assert state["networkActionsTaken"] == 0
    assert state["config"]["networkActionsPerTurn"] == 2
    chart = next(a for a in state["legalActions"] if a["type"] == "chart")
    state = client.post(f"/api/games/{game_id}/actions", json={"action": chart}).json()
    assert state["phase"] == "network"
    assert state["networkActionsTaken"] == 1


def test_undo_endpoint(client):
    body = client.post("/api/games", json={"seats": [{"name": "A"}, {"name": "B"}]}).json()
    game_id, state = body["gameId"], body["state"]
    assert not state["canUndo"]
    assert client.post(f"/api/games/{game_id}/undo").status_code == 400
    start = next(a for a in state["legalActions"] if a["type"] == "buy")
    after = client.post(f"/api/games/{game_id}/actions", json={"action": start}).json()
    assert after["canUndo"]
    restored = client.post(f"/api/games/{game_id}/undo").json()
    assert restored["log"] == state["log"]
    assert restored["currentPlayer"] == state["currentPlayer"]
    assert not restored["canUndo"]


def _start(client, seed=3):
    seats = [{"name": "Me"}, {"name": "Bot", "bot": True}]
    return client.post("/api/games", json={"seats": seats, "seed": seed}).json()


def _first_buy(state):
    return next(a for a in state["legalActions"] if a["type"] == "buy")


def test_game_survives_a_new_app_instance(store):
    first = TestClient(create_app(store, store, HeaderUser()), headers={"Authorization": "alice"})
    body = _start(first)
    state = first.post(
        f"/api/games/{body['gameId']}/actions", json={"action": _first_buy(body["state"])}
    ).json()
    second = TestClient(create_app(store, store, HeaderUser()), headers={"Authorization": "alice"})
    assert second.get(f"/api/games/{body['gameId']}").json() == {**state, "moves": []}


def test_requests_without_a_user_are_refused(store):
    anonymous = TestClient(create_app(store, store, HeaderUser()))
    assert anonymous.get("/api/games").status_code == 401
    assert anonymous.get("/api/board").status_code == 200


def test_other_users_games_are_invisible(client):
    body = _start(client)
    bob = {"Authorization": "bob"}
    assert client.get(f"/api/games/{body['gameId']}", headers=bob).status_code == 404
    action = {"action": _first_buy(body["state"])}
    assert (
        client.post(f"/api/games/{body['gameId']}/actions", json=action, headers=bob).status_code
        == 404
    )
    assert client.delete(f"/api/games/{body['gameId']}", headers=bob).status_code == 404
    assert client.get("/api/games", headers=bob).json() == {"games": []}


def test_list_games_newest_first(client):
    older = _start(client, seed=1)
    newer = _start(client, seed=2)
    client.post(
        f"/api/games/{older['gameId']}/actions", json={"action": _first_buy(older["state"])}
    )
    games = client.get("/api/games").json()["games"]
    assert [g["gameId"] for g in games] == [older["gameId"], newer["gameId"]]
    assert games[0]["players"] == [{"name": "Me", "bot": False}, {"name": "Bot", "bot": True}]
    assert games[0]["phase"] == "stock"
    assert games[0]["roundLabel"] == "SR1"


def test_delete_game(client):
    body = _start(client)
    assert client.delete(f"/api/games/{body['gameId']}").status_code == 204
    assert client.get(f"/api/games/{body['gameId']}").status_code == 404
    assert client.get("/api/games").json() == {"games": []}


def test_write_from_a_stale_load_is_refused(client, store, monkeypatch):
    body = _start(client)
    game_id = body["gameId"]
    stale = store.get("alice", game_id)
    client.post(f"/api/games/{game_id}/actions", json={"action": _first_buy(body["state"])})
    # The next request loads the save as it was before the move above, as a second tab would.
    monkeypatch.setattr(store, "get", lambda owner, gid: stale)
    r = client.post(f"/api/games/{game_id}/actions", json={"action": _first_buy(body["state"])})
    assert r.status_code == 409


def test_engine_change_replays_the_save(client, store, monkeypatch):
    body = _start(client)
    game_id = body["gameId"]
    state = client.post(
        f"/api/games/{game_id}/actions", json={"action": _first_buy(body["state"])}
    ).json()
    monkeypatch.setattr("bby18.api.saves.CODE_VERSION", "a-newer-engine")
    assert client.get(f"/api/games/{game_id}").json() == {**state, "moves": []}


def test_save_that_no_longer_replays_is_reported(client, store, monkeypatch):
    body = _start(client)
    game_id = body["gameId"]
    saved = store.get("alice", game_id)
    from dataclasses import replace

    store._games[game_id] = replace(
        saved, code_version="old", actions=({"type": "dividend", "choice": "pay"},)
    )
    r = client.get(f"/api/games/{game_id}")
    assert r.status_code == 409
    assert "older rules" in r.json()["detail"]


def test_undo_takes_back_bot_replies_too(client):
    body = _start(client)
    game_id = body["gameId"]
    client.post(f"/api/games/{game_id}/actions", json={"action": _first_buy(body["state"])})
    restored = client.post(f"/api/games/{game_id}/undo").json()
    assert restored == body["state"]


def test_settings_require_an_explicit_mode(monkeypatch):
    from bby18.api.app import settings_from_env

    monkeypatch.delenv("BBY18_MODE", raising=False)
    with pytest.raises(RuntimeError, match="BBY18_MODE"):
        settings_from_env()
    monkeypatch.setenv("BBY18_MODE", "postgres")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        settings_from_env()
    monkeypatch.setenv("BBY18_MODE", "local")
    assert settings_from_env().mode == "local"


def test_anonymous_account_flow():
    """A browser creates an account, then acts with its token; other tokens are refused."""
    from bby18.api.auth import TokenAuthenticator

    memory = MemoryStore()
    client = TestClient(create_app(memory, memory, TokenAuthenticator(memory)))
    account = client.post("/api/accounts").json()
    assert set(account) == {"accountId", "token"}
    mine = {"Authorization": f"Bearer {account['token']}"}
    assert client.get("/api/games").status_code == 401
    assert client.get("/api/games", headers={"Authorization": "Bearer made-up"}).status_code == 401
    body = client.post(
        "/api/games", json={"seats": [{"name": "A"}, {"name": "B"}]}, headers=mine
    ).json()
    assert [g["gameId"] for g in client.get("/api/games", headers=mine).json()["games"]] == [
        body["gameId"]
    ]
    other = {"Authorization": f"Bearer {client.post('/api/accounts').json()['token']}"}
    assert client.get(f"/api/games/{body['gameId']}", headers=other).status_code == 404
    assert client.get("/api/games", headers=other).json() == {"games": []}


def test_easy_bot_seats_get_distinct_named_characters(client):
    seats = [{"name": "Me"}] + [{"name": "x", "bot": True, "difficulty": "easy"}] * 2
    state = client.post("/api/games", json={"seats": seats, "seed": 9}).json()["state"]
    me, *bots = state["players"]
    assert me["difficulty"] == "" and me["plan"] == ""
    names = {b["name"] for b in bots}
    assert len(names) == 2 and "x" not in names
    assert all(b["difficulty"] == "easy" and b["plan"] == "" for b in bots)


def test_same_seed_draws_the_same_characters(client):
    seats = [{"name": "Me"}, {"name": "x", "bot": True, "difficulty": "easy"}]
    first = client.post("/api/games", json={"seats": seats, "seed": 3}).json()["state"]
    second = client.post("/api/games", json={"seats": seats, "seed": 3}).json()["state"]
    assert first["players"][1]["name"] == second["players"][1]["name"]


def test_bot_plans_are_revealed_when_the_game_ends(client):
    seats = [{"name": "x", "bot": True, "difficulty": "easy"}] * 2 + [{"name": "Old", "bot": True}]
    state = client.post("/api/games", json={"seats": seats, "seed": 4}).json()["state"]
    assert state["phase"] == "game_over"
    roster_bots, classic = state["players"][:2], state["players"][2]
    assert all(b["plan"] for b in roster_bots)
    assert classic["name"] == "Old" and classic["plan"] == "" and classic["difficulty"] == ""


@pytest.mark.parametrize(
    "seat",
    [{"name": "Me", "difficulty": "easy"}, {"name": "B", "bot": True, "difficulty": "brutal"}],
    ids=["human-with-difficulty", "unknown-difficulty"],
)
def test_bad_difficulty_is_rejected(client, seat):
    seats = [seat, {"name": "B2", "bot": True}]
    assert client.post("/api/games", json={"seats": seats}).status_code == 422


def test_action_response_lists_the_submitted_move_then_bot_replies(client):
    body = _start(client)
    start = _first_buy(body["state"])
    state = client.post(f"/api/games/{body['gameId']}/actions", json={"action": start}).json()
    first, *replies = state["moves"]
    assert first["action"] == start
    assert not first["automatic"]
    assert first["actor"] == "P1"
    assert first["phase"] == "stock" and first["roundLabel"] == "SR1"
    assert first["corporation"] is None
    assert replies and all(m["automatic"] for m in replies)
    assert replies[0]["actor"] == "P2"
    # Each frame's turn fields show who acts next, which is who makes the following move.
    for move, following in zip(state["moves"], replies):
        assert move["after"]["currentPlayer"] == following["actor"]
    assert state["moves"][-1]["after"]["currentPlayer"] == state["currentPlayer"] == "P1"


def test_frame_logs_are_the_state_log_lines_the_request_wrote(client):
    body = _start(client)
    state = client.post(
        f"/api/games/{body['gameId']}/actions", json={"action": _first_buy(body["state"])}
    ).json()
    frame_log = [entry for move in state["moves"] for entry in move["log"]]
    assert all(move["log"] for move in state["moves"])
    assert frame_log == state["log"][len(body["state"]["log"]) :]
    assert frame_log[len(state["moves"][0]["log"])]["seq"] == state["automaticLogStart"]


def test_network_frame_lists_only_the_charted_tile(client):
    body = client.post(
        "/api/games", json={"seats": [{"name": "A"}, {"name": "B"}], "seed": 1}
    ).json()
    game_id, state = body["gameId"], body["state"]
    while state["phase"] != "network":
        legal = state["legalActions"]
        action = next((a for a in legal if a["type"] == "buy"), None) or next(
            a for a in legal if a["type"] == "pass"
        )
        state = client.post(f"/api/games/{game_id}/actions", json={"action": action}).json()
    corp = state["currentCorporation"]
    chart = next(a for a in state["legalActions"] if a["type"] == "chart")
    state = client.post(f"/api/games/{game_id}/actions", json={"action": chart}).json()
    (move,) = state["moves"]
    assert move["phase"] == "network" and move["corporation"] == corp
    assert move["revenue"] == 0
    tile = next(t for t in state["tiles"] if t["hex"] == chart["hex"])
    assert move["after"]["tiles"] == [tile]
    assert move["after"]["networkActionsTaken"] == 1


def test_new_game_with_a_bot_first_returns_its_opening_moves(client):
    seats = [{"name": "Bot", "bot": True, "difficulty": "easy"}, {"name": "Me"}]
    state = client.post("/api/games", json={"seats": seats, "seed": 3}).json()["state"]
    assert state["moves"]
    assert all(m["automatic"] and m["actor"] == "P1" for m in state["moves"])
    # Before the first move, setting up the board logs where the Death Star is being built.
    setup, played = state["log"][:1], state["log"][1:]
    assert "begins the Death Star" in setup[0]["text"]
    assert [e for m in state["moves"] for e in m["log"]] == played
    assert state["moves"][-1]["after"]["currentPlayer"] == state["currentPlayer"] == "P2"


def test_new_game_with_a_human_first_has_no_moves(client):
    assert _start(client)["state"]["moves"] == []


def test_load_and_undo_return_no_moves(client):
    body = _start(client)
    game_id = body["gameId"]
    client.post(f"/api/games/{game_id}/actions", json={"action": _first_buy(body["state"])})
    assert client.get(f"/api/games/{game_id}").json()["moves"] == []
    assert client.post(f"/api/games/{game_id}/undo").json()["moves"] == []
