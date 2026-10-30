"""The API under the supply-chain rules (``chain_rules``): chains in each corporation's revenue,
and the surrender phase in which each corporation chooses the facility a seizure takes."""

import random
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from bby18.actions import SurrenderFacility
from bby18.api.app import create_app
from bby18.api.auth import AuthError
from bby18.api.saves import new_session
from bby18.api.serialize import (
    action_to_json,
    chain_to_json,
    match_action,
    rules_to_json,
    session_to_json,
)
from bby18.api.store import MemoryStore, Seat
from bby18.board import Planet
from bby18.config import DEFAULT_CONFIG
from bby18.game import EMPIRE
from bby18.hexgrid import Hex
from bby18.revenue import ScoredChain, ScoredPair

CHAIN_CONFIG = replace(DEFAULT_CONFIG, chain_rules=True, fleet_limit=4)
"""The rules the web app will serve once the chain rules are adopted."""
SEATS = [{"name": "Me"}, {"name": "Bot", "bot": True, "difficulty": "easy"}]


class HeaderUser:
    """Takes the caller's user id straight from the Authorization header."""

    def user_id(self, authorization: str) -> str:
        if not authorization:
            raise AuthError("no user")
        return authorization


@pytest.fixture(autouse=True)
def chain_rules(monkeypatch):
    """Serve new games, replays and the rules page under the chain rules."""
    monkeypatch.setattr("bby18.api.saves.DEFAULT_CONFIG", CHAIN_CONFIG)
    monkeypatch.setattr("bby18.api.app.DEFAULT_CONFIG", CHAIN_CONFIG)


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def client(store):
    return TestClient(create_app(store, store, HeaderUser()), headers={"Authorization": "alice"})


def _corp(state: dict, corp_id: str) -> dict:
    return next(c for c in state["corporations"] if c["id"] == corp_id)


def _held_planets(state: dict, corp_id: str) -> set[tuple[int, int]]:
    return {
        tuple(p["hex"])
        for p in state["facilities"]["planets"]
        if any(f["owner"] == corp_id for f in p["facilities"])
    }


def _choose(state: dict, rng: random.Random) -> dict:
    """A plausible human move: start a corporation and buy into it, build at random, spread up
    to three facilities over different planets (so a seizure gives a real choice), and pay."""
    legal = state["legalActions"]
    by_type: dict[str, list[dict]] = {}
    for action in legal:
        by_type.setdefault(action["type"], []).append(action)
    if state["phase"] == "stock":
        buys = by_type.get("buy", [])
        mine = {c["id"] for c in state["corporations"] if c["president"] == state["currentPlayer"]}
        own = [a for a in buys if a["corp"] in mine and a["source"] == "ipo"]
        starts = [a for a in buys if "par" in a]
        if own:
            return own[0]
        if starts and not mine:
            return starts[len(starts) // 2]
        return by_type["pass"][0]
    if state["phase"] == "fleet":
        corp_id = state["currentCorporation"]
        held = _held_planets(state, corp_id)
        fresh = [a for a in by_type.get("build_facility", []) if tuple(a["planet"]) not in held]
        if fresh and (_corp(state, corp_id)["fleets"] < 3 or "finish_fleets" not in by_type):
            return rng.choice(fresh)
        if "finish_fleets" in by_type:
            return by_type["finish_fleets"][0]
        return rng.choice(by_type["build_facility"])
    if state["phase"] == "dividend":
        return next(a for a in legal if a["choice"] == "pay") if len(legal) > 1 else legal[0]
    return rng.choice(legal)


def _check_chains(state: dict) -> None:
    """Invariants of the revenue blocks under the chain rules."""
    for corp in state["corporations"]:
        revenue = corp["revenue"]
        chains = revenue["chains"]
        links = [link for chain in chains for link in chain["links"]]
        assert links == revenue["pairs"], "pairs are every chain's links, flattened"
        if corp["status"] == "floated":
            assert len(chains) <= corp["fleets"]
            assert corp["fleetRevenue"]["uncappedPairs"] >= len(chains)
        stops = [stop for chain in chains for stop in chain["stops"]]
        assert len(stops) == len(set(stops)), "no planet is in two chains"
        for chain in chains:
            assert len(chain["links"]) == len(chain["stops"]) - 1
            for link, a, b in zip(chain["links"], chain["stops"], chain["stops"][1:]):
                assert (link["a"], link["b"]) == (a, b)
            assert (
                chain["value"] == sum(link["value"] for link in chain["links"]) + chain["regional"]
            )
        assert revenue["total"] >= sum(chain["value"] for chain in chains)


def _check_surrender(state: dict) -> None:
    """Invariants of the surrender phase a client may rely on."""
    facilities = state["facilities"]
    assert facilities["seizureTargets"] == [], "under the chain rules each corporation chooses"
    if state["phase"] != "surrender":
        assert facilities["surrenderOptions"] == []
        assert facilities["surrenderQueue"] == []
        return
    corp_id = state["currentCorporation"]
    corp = _corp(state, corp_id)
    assert facilities["surrenderQueue"][0] == corp_id
    assert state["currentPlayer"] == corp["president"]
    options = facilities["surrenderOptions"]
    assert [o["action"] for o in options] == state["legalActions"]
    assert {tuple(o["action"]["planet"]) for o in options} == _held_planets(state, corp_id)
    names = {p["name"]: p for p in facilities["planets"]}
    for option in options:
        assert names[option["name"]]["hex"] == option["action"]["planet"]
        assert option["revenue"] <= corp["revenue"]["total"] or corp["fleets"] == 0


# --- actions and rules ------------------------------------------------------------------------


def test_surrender_action_round_trips():
    planet = Hex(-3, 2)
    action = SurrenderFacility(planet)
    assert action_to_json(action) == {"type": "surrender_facility", "planet": [-3, 2]}
    other = SurrenderFacility(Hex(0, 0))
    assert match_action([other, action], action_to_json(action)) is action
    with pytest.raises(ValueError):
        match_action([other], action_to_json(action))


def test_chain_json_lists_stops_in_travel_order_and_each_link():
    kessel = Planet("Kessel", Hex(0, 0), "Outer Rim", frozenset({"R"}))
    sullust = Planet("Sullust", Hex(1, 0), "Mid Rim", frozenset({"I"}))
    corellia = Planet("Corellia", Hex(2, 0), "Core", frozenset({"S"}))
    chain = ScoredChain(
        stops=(kessel, sullust, corellia),
        links=(ScoredPair(kessel, sullust, 30, True), ScoredPair(sullust, corellia, 30, True)),
        regional=20,
    )
    assert chain_to_json(chain) == {
        "stops": ["Kessel", "Sullust", "Corellia"],
        "links": [
            {"a": "Kessel", "b": "Sullust", "value": 30, "typed": True, "contract": False},
            {"a": "Sullust", "b": "Corellia", "value": 30, "typed": True, "contract": False},
        ],
        "regional": 20,
        "value": 80,
    }


def test_rules_say_whether_the_chain_rules_apply_and_give_the_commodity_order(client):
    rules = client.get("/api/rules").json()
    assert rules["chainRules"] is True
    assert rules["commodityOrder"] == CHAIN_CONFIG.commodity_order
    ranks = list(rules["commodityOrder"].values())
    assert ranks == sorted(ranks), "listed from raw goods up to the site"
    assert rules_to_json(DEFAULT_CONFIG)["chainRules"] is DEFAULT_CONFIG.chain_rules


def test_pair_rules_state_has_no_chains(monkeypatch):
    monkeypatch.setattr("bby18.api.saves.DEFAULT_CONFIG", replace(CHAIN_CONFIG, chain_rules=False))
    session = new_session(4, (Seat("Me", False), Seat("Bot", True)))
    session.run_bots()
    state = session_to_json(session)
    assert state["config"]["chainRules"] is False
    assert all(c["revenue"]["chains"] == [] for c in state["corporations"])
    assert state["facilities"]["surrenderQueue"] == []
    assert state["facilities"]["surrenderOptions"] == []


# --- a whole game -----------------------------------------------------------------------------


def _play_to_human_surrender(client, seed: int) -> tuple[str, dict, random.Random]:
    body = client.post("/api/games", json={"seats": SEATS, "seed": seed}).json()
    game_id = body["gameId"]
    rng = random.Random(seed)
    state = body["state"]
    while state["phase"] != "game_over":
        if state["phase"] == "surrender" and state["waitingOnHuman"]:
            return game_id, state, rng
        state = client.post(
            f"/api/games/{game_id}/actions", json={"action": _choose(state, rng)}
        ).json()
    pytest.fail(f"seed {seed} never asked the human to surrender a facility")


def test_a_whole_api_game_through_a_surrender_phase(client):
    body = client.post("/api/games", json={"seats": SEATS, "seed": 12}).json()
    game_id = body["gameId"]
    rng = random.Random(12)
    state = body["state"]
    human_choices = surrender_frames = long_chains = 0
    demanded = False
    while state["phase"] != "game_over":
        _check_chains(state)
        _check_surrender(state)
        human_choices += state["phase"] == "surrender"
        action = _choose(state, rng)
        state = client.post(f"/api/games/{game_id}/actions", json={"action": action}).json()
        for frame in state["moves"]:
            demanded |= any("demands a facility from" in line["text"] for line in frame["log"])
            if frame["phase"] != "surrender":
                continue
            surrender_frames += 1
            assert frame["corporation"] is not None
            assert frame["action"]["type"] == "surrender_facility"
            (line,) = frame["log"]
            assert line["actor"] == EMPIRE
            assert line["text"].startswith(f"takes over {frame['corporation']}'s facility at ")
            planet = next(
                p
                for p in frame["after"]["facilities"]["planets"]
                if p["hex"] == frame["action"]["planet"]
            )
            assert EMPIRE in [f["owner"] for f in planet["facilities"]]
        long_chains += sum(
            len(chain["stops"]) > 2
            for c in state["corporations"]
            for chain in c["revenue"]["chains"]
        )
    _check_chains(state)
    assert demanded and surrender_frames > 0
    assert human_choices > 0, "the human's corporation chose at a seizure"
    assert long_chains > 0, "some chain ran through a middle stop"


def test_surrender_prompt_through_the_api(client):
    game_id, state, _ = _play_to_human_surrender(client, 12)
    corp_id = state["currentCorporation"]
    corp = _corp(state, corp_id)
    options = state["facilities"]["surrenderOptions"]
    assert len(options) > 1, "a forced surrender plays itself"
    _check_surrender(state)
    choice = min(options, key=lambda o: o["revenue"])

    after = client.post(f"/api/games/{game_id}/actions", json={"action": choice["action"]}).json()
    move = after["moves"][0]
    assert move["phase"] == "surrender" and move["corporation"] == corp_id
    assert move["action"] == choice["action"] and move["automatic"] is False
    owners = next(p for p in after["facilities"]["planets"] if p["name"] == choice["name"])
    assert EMPIRE in [f["owner"] for f in owners["facilities"]]
    assert _corp(move["after"], corp_id)["fleets"] == corp["fleets"] - 1
    # The prompt's figure is the revenue the corporation is left with until something changes.
    assert _corp(move["after"], corp_id)["revenue"]["total"] == choice["revenue"]


def test_a_game_saved_in_a_surrender_phase_replays(client, monkeypatch):
    game_id, state, _ = _play_to_human_surrender(client, 12)
    monkeypatch.setattr("bby18.api.saves.CODE_VERSION", "a-newer-engine")
    assert client.get(f"/api/games/{game_id}").json() == {**state, "moves": []}


def test_undo_returns_to_the_surrender_prompt(client):
    game_id, state, _ = _play_to_human_surrender(client, 12)
    option = state["facilities"]["surrenderOptions"][0]
    client.post(f"/api/games/{game_id}/actions", json={"action": option["action"]})
    back = client.post(f"/api/games/{game_id}/undo").json()
    assert back == {**state, "moves": []}


# --- saves from before the chain rules --------------------------------------------------------


def test_a_save_from_the_pair_rules_replays_or_answers_409(client, store, monkeypatch):
    """A save keeps no rules; after the chain rules are served it replays under them. Its
    pickled session is never read, since the engine's code version changed with the rules."""
    pair_rules = replace(CHAIN_CONFIG, chain_rules=False)
    monkeypatch.setattr("bby18.api.saves.DEFAULT_CONFIG", pair_rules)
    body = client.post("/api/games", json={"seats": SEATS, "seed": 9}).json()
    game_id = body["gameId"]
    rng = random.Random(9)
    state = body["state"]
    while state["roundNumber"] < 4 and state["phase"] != "game_over":
        state = client.post(
            f"/api/games/{game_id}/actions", json={"action": _choose(state, rng)}
        ).json()
    monkeypatch.setattr("bby18.api.saves.DEFAULT_CONFIG", CHAIN_CONFIG)
    monkeypatch.setattr("bby18.api.saves.CODE_VERSION", "the-chain-rules-engine")
    response = client.get(f"/api/games/{game_id}")
    assert response.status_code in (200, 409)
    if response.status_code == 200:
        assert response.json()["config"]["chainRules"] is True
    else:
        assert "older rules" in response.json()["detail"]
