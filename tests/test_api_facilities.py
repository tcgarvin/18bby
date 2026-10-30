"""The API under the facility rules (``facility_rules``), the rules it serves since 2026-10-27."""

import random

import pytest
from fastapi.testclient import TestClient

from bby18.actions import BuildFacility, BuyShare, ShareSource
from bby18.api.app import create_app
from bby18.api.auth import AuthError
from bby18.api.saves import new_session
from bby18.api.serialize import action_to_json, match_action, rules_to_json, session_to_json
from bby18.api.store import MemoryStore, Seat
from bby18.config import FACILITY_CONFIG, FLEET_CONFIG
from bby18.death_star import SITE_NAME
from bby18.game import EMPIRE, Game
from bby18.hexgrid import Direction, Hex
from bby18.session import GameSession
from bby18.state import Corporation

SEATS = [{"name": "Me"}, {"name": "Bot", "bot": True, "difficulty": "easy"}]


class HeaderUser:
    """Takes the caller's user id straight from the Authorization header."""

    def user_id(self, authorization: str) -> str:
        if not authorization:
            raise AuthError("no user")
        return authorization


@pytest.fixture
def fleet_rules(monkeypatch):
    """Serve new games, replays and the rules page under the fleet rules of 2026-10-26."""
    monkeypatch.setattr("bby18.api.saves.DEFAULT_CONFIG", FLEET_CONFIG)
    monkeypatch.setattr("bby18.api.app.DEFAULT_CONFIG", FLEET_CONFIG)


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def client(store):
    return TestClient(create_app(store, store, HeaderUser()), headers={"Authorization": "alice"})


def _corp(state: dict, corp_id: str) -> dict:
    return next(c for c in state["corporations"] if c["id"] == corp_id)


def _planet(state: dict, name: str) -> dict:
    return next(p for p in state["facilities"]["planets"] if p["name"] == name)


def _choose(state: dict, rng: random.Random) -> dict:
    """A plausible human move: start a corporation and buy into it, build at random, keep one
    or two facilities wherever chance puts them, and pay dividends."""
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
        corp = _corp(state, state["currentCorporation"])
        if "build_facility" in by_type and (corp["fleets"] < 2 or "finish_fleets" not in by_type):
            return rng.choice(by_type["build_facility"])
        return by_type["finish_fleets"][0]
    if state["phase"] == "dividend":
        return next(a for a in legal if a["choice"] == "pay") if len(legal) > 1 else legal[0]
    return rng.choice(legal)


def _merge_planets(planets: dict, frame: dict) -> None:
    """What a client does with a move frame: replace each planet it lists, by hex."""
    for planet in frame["after"]["facilities"]["planets"]:
        planets[tuple(planet["hex"])] = planet


def _check_facilities(state: dict) -> None:
    """Invariants a client may rely on in any state under the facility rules."""
    facilities = state["facilities"]
    owned: dict[str, int] = {}
    for planet in facilities["planets"]:
        assert planet["name"] != SITE_NAME
        assert len(planet["claimed"]) + planet["unclaimed"] == planet["exits"]
        assert planet["exits"] == FACILITY_CONFIG.planet_base_exits + len(planet["facilities"])
        assert len(planet["facilities"]) <= facilities["perPlanet"]
        assert planet["freeSlots"] <= facilities["perPlanet"] - len(planet["facilities"])
        assert not set(planet["dangling"]) & set(planet["claimed"])
        for facility in planet["facilities"]:
            owned[facility["owner"]] = owned.get(facility["owner"], 0) + 1
    for corp in state["corporations"]:
        if corp["status"] == "floated":
            assert corp["fleets"] == owned.get(corp["id"], 0)
    builds = [a for a in state["legalActions"] if a["type"] == "build_facility"]
    assert [o["action"] for o in facilities["options"]] == builds
    for option in facilities["options"]:
        planet = next(p for p in facilities["planets"] if p["hex"] == option["action"]["planet"])
        assert planet["freeSlots"] > 0
        if "exit" in option["action"]:
            assert option["action"]["exit"] in planet["dangling"]
        else:
            assert option["lane"] == [] and option["reaches"] == []


# --- actions and rules ------------------------------------------------------------------------


def test_build_facility_json_names_the_exit_only_when_given():
    planet = Hex(-3, 2)
    unclaimed = BuildFacility(planet, None, 60)
    toward = BuildFacility(planet, Direction.W, 90)
    assert action_to_json(unclaimed) == {"type": "build_facility", "planet": [-3, 2], "cost": 60}
    assert action_to_json(toward) == {
        "type": "build_facility",
        "planet": [-3, 2],
        "exit": "W",
        "cost": 90,
    }
    legal = [unclaimed, toward]
    assert match_action(legal, action_to_json(toward)) is toward
    assert match_action(legal, action_to_json(unclaimed)) is unclaimed
    with pytest.raises(ValueError):
        match_action(legal, {"type": "build_facility", "planet": [-3, 2], "exit": None, "cost": 60})


def test_rules_say_whether_the_facility_rules_apply(client):
    rules = client.get("/api/rules").json()
    assert rules["facilityRules"] is True
    assert rules["facilities"] == {
        "perPlanet": FACILITY_CONFIG.facilities_per_planet,
        "baseExits": FACILITY_CONFIG.planet_base_exits,
    }
    assert rules["deathStar"]["fleetLimit"] == FACILITY_CONFIG.fleet_limit
    off = rules_to_json(FLEET_CONFIG)
    assert off["facilityRules"] is False
    assert set(off["facilities"]) == set(rules["facilities"])


def test_fleet_rules_state_has_no_facilities(fleet_rules):
    seats = (Seat("Me", False), Seat("You", False))
    state = session_to_json(new_session(2, seats))
    assert "facilities" not in state
    assert state["deathStar"]["fleets"]["item"] == "fleet"


# --- game state -------------------------------------------------------------------------------


def test_new_game_lists_every_planet_with_one_open_exit(client):
    state = client.post("/api/games", json={"seats": SEATS, "seed": 4}).json()["state"]
    facilities = state["facilities"]
    board = client.get("/api/board").json()
    assert {p["name"] for p in facilities["planets"]} == {p["name"] for p in board["planets"]}
    assert facilities["perPlanet"] == FACILITY_CONFIG.facilities_per_planet
    homeworlds = {c["homeworld"] for c in state["corporations"]}
    for planet in facilities["planets"]:
        floated_home = any(
            c["homeworld"] == planet["name"] and c["status"] == "floated"
            for c in state["corporations"]
        )
        assert planet["exits"] == 1 + floated_home
        if planet["name"] in homeworlds and not floated_home:
            assert planet["freeSlots"] == facilities["perPlanet"] - 1
    assert state["deathStar"]["fleets"]["item"] == "facility"
    assert facilities["options"] == []
    _check_facilities(state)


def test_facility_step_through_the_api(client):
    body = client.post("/api/games", json={"seats": SEATS, "seed": 4}).json()
    game_id = body["gameId"]
    rng = random.Random(4)
    state = body["state"]
    while not (state["phase"] == "fleet" and state["waitingOnHuman"]):
        state = client.post(
            f"/api/games/{game_id}/actions", json={"action": _choose(state, rng)}
        ).json()
    corp_id = state["currentCorporation"]
    corp = _corp(state, corp_id)
    options = state["facilities"]["options"]
    assert options, "a corporation that just floated can build"
    _check_facilities(state)
    unclaimed = next(o for o in options if "exit" not in o["action"])
    # Leaving the exit open changes no lane, so it earns exactly what one more pair does.
    assert unclaimed["revenue"] == corp["fleetRevenue"]["withNextFleet"]
    assert unclaimed["reaches"] == [] and unclaimed["lane"] == []
    build = unclaimed["action"]
    assert build["cost"] == state["deathStar"]["fleets"]["price"]
    planet_before = next(p for p in state["facilities"]["planets"] if p["hex"] == build["planet"])

    after = client.post(f"/api/games/{game_id}/actions", json={"action": build}).json()
    built = _corp(after, corp_id)
    assert built["fleets"] == corp["fleets"] + 1
    assert built["treasury"] == corp["treasury"] - build["cost"]
    planet = _planet(after, planet_before["name"])
    assert planet["exits"] == planet_before["exits"] + 1
    assert planet["unclaimed"] == planet_before["unclaimed"] + 1
    assert planet["facilities"][-1]["owner"] == corp_id
    assert after["deathStar"]["fleets"]["sold"] == state["deathStar"]["fleets"]["sold"] + 1
    move, *_ = after["moves"]
    assert move["phase"] == "fleet" and move["action"] == build
    assert move["after"]["facilities"]["planets"] == [planet]
    assert any("builds a facility at" in line["text"] for line in move["log"])


def test_a_whole_api_game_under_facility_rules(client):
    body = client.post("/api/games", json={"seats": SEATS, "seed": 11}).json()
    game_id = body["gameId"]
    rng = random.Random(11)
    state = body["state"]
    planets = {tuple(p["hex"]): p for p in state["facilities"]["planets"]}
    built = seized = 0
    while state["phase"] != "game_over":
        _check_facilities(state)
        action = _choose(state, rng)
        state = client.post(f"/api/games/{game_id}/actions", json={"action": action}).json()
        for frame in state["moves"]:
            _merge_planets(planets, frame)
            built += frame["action"]["type"] == "build_facility"
            seized += sum("takes over" in line["text"] for line in frame["log"])
        # A client merging each frame's changed planets keeps the board the server has.
        assert planets == {tuple(p["hex"]): p for p in state["facilities"]["planets"]}
    _check_facilities(state)
    owners = {f["owner"] for p in state["facilities"]["planets"] for f in p["facilities"]}
    assert built > 0
    assert seized > 0 and EMPIRE in owners
    assert state["facilities"]["options"] == []


def test_facility_game_replays_from_its_save(client, monkeypatch):
    body = client.post("/api/games", json={"seats": SEATS, "seed": 9}).json()
    game_id = body["gameId"]
    rng = random.Random(9)
    state = body["state"]
    submitted = []
    while state["roundNumber"] < 3 and state["phase"] != "game_over":
        action = _choose(state, rng)
        submitted.append(action)
        state = client.post(f"/api/games/{game_id}/actions", json={"action": action}).json()
    assert any(a["type"] == "build_facility" for a in submitted)
    monkeypatch.setattr("bby18.api.saves.CODE_VERSION", "a-newer-engine")
    assert client.get(f"/api/games/{game_id}").json() == {**state, "moves": []}


# --- seizure ----------------------------------------------------------------------------------


def _floated_game() -> tuple[GameSession, Corporation]:
    """A three-player game under the facility rules with one corporation floated."""
    game = Game.new(["Ann", "Ben", "Cy"], FACILITY_CONFIG, 2)
    corp = next(iter(game.corporations.values()))
    first, second, third = game.players
    for player, par in ((first, 60), (second, 0), (third, 0), (second, 0)):
        game.apply_stock_action(player, BuyShare(corp.id, ShareSource.IPO, par), set())
    assert corp.floated
    return GameSession(game), corp


def test_seizure_targets_are_the_facilities_nearest_the_site_and_turn_imperial():
    session, corp = _floated_game()
    game = session.game
    home = list(game.homeworld(corp))
    state = session_to_json(session)
    assert state["facilities"]["seizureTargets"] == [{"corp": corp.id, "hex": home}]
    game.death_star.cubes = FACILITY_CONFIG.death_star_cubes_per_stage
    game.resolve_death_star()
    state = session_to_json(session)
    home_planet = next(p for p in state["facilities"]["planets"] if p["hex"] == home)
    assert [f["owner"] for f in home_planet["facilities"]] == [EMPIRE]
    assert home_planet["exits"] == 2, "a seized facility keeps its exit"
    assert _corp(state, corp.id)["fleets"] == 0
    assert state["facilities"]["seizureTargets"] == []
