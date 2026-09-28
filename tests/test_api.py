import pytest
from fastapi.testclient import TestClient

from bby18.api.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_board_endpoint(client):
    data = client.get("/api/board").json()
    assert len(data["hexes"]) == 127
    assert len(data["planets"]) == 24


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


def test_illegal_action_returns_400(client):
    body = client.post("/api/games", json={"seats": [{"name": "A"}, {"name": "B"}]}).json()
    r = client.post(
        f"/api/games/{body['gameId']}/actions",
        json={"action": {"type": "dividend", "choice": "pay"}},
    )
    assert r.status_code == 400
    assert client.get("/api/games/nope").status_code == 404
