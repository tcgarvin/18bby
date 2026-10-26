"""The API under the Death Star rules, the only rules it serves since 2026-10-26."""

import random

import pytest
from fastapi.testclient import TestClient

from bby18.api.app import create_app
from bby18.api.auth import AuthError
from bby18.api.saves import new_session
from bby18.api.serialize import fleet_tiers_to_json, rules_to_json, session_to_json
from bby18.api.store import MemoryStore, Seat
from bby18.config import CLASSIC_CONFIG, DEFAULT_CONFIG
from bby18.revenue import RevenueResult, ScoredPair
from bby18.session import GameSession
from bby18.state import CorpStatus

RULES_ON = DEFAULT_CONFIG
"""The rules the API serves."""

# The rules-off state as it was before the Death Star fields were added; new fields may only be
# added alongside these, never replace them.
STATE_KEYS = {
    "phase",
    "roundLabel",
    "roundNumber",
    "currentPlayer",
    "currentCorporation",
    "priorityPlayer",
    "operatingOrder",
    "networkActionsTaken",
    "totalRounds",
    "waitingOnHuman",
    "legalActions",
    "players",
    "corporations",
    "tiles",
    "terrain",
    "stockMarket",
    "parColumn",
    "canUndo",
    "automaticLogStart",
    "config",
    "log",
    "moves",
}
CORPORATION_KEYS = {
    "id",
    "name",
    "homeworld",
    "status",
    "par",
    "ipoPrice",
    "price",
    "marketCell",
    "dividendPreview",
    "treasury",
    "ipoShares",
    "poolShares",
    "president",
    "lastRevenue",
    "fleets",
    "reachablePlanets",
    "revenue",
}
SEATS = [{"name": "Me"}, {"name": "Bot", "bot": True, "difficulty": "easy"}]


class HeaderUser:
    """Takes the caller's user id straight from the Authorization header."""

    def user_id(self, authorization: str) -> str:
        if not authorization:
            raise AuthError("no user")
        return authorization


@pytest.fixture
def classic_rules(monkeypatch):
    """Serve new games and replays under the rules before the Death Star was adopted."""
    monkeypatch.setattr("bby18.api.saves.DEFAULT_CONFIG", CLASSIC_CONFIG)


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def client(store):
    return TestClient(create_app(store, store, HeaderUser()), headers={"Authorization": "alice"})


def _choose(state: dict, rng: random.Random) -> dict:
    """A plausible human move: start a corporation and buy into it, build at random, keep one
    or two fleets, and pay dividends."""
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
        corp = next(c for c in state["corporations"] if c["id"] == state["currentCorporation"])
        if "buy_fleet" in by_type and corp["fleets"] < 2:
            return by_type["buy_fleet"][0]
        return by_type["finish_fleets"][0]
    if state["phase"] == "dividend":
        return next(a for a in legal if a["choice"] == "pay") if len(legal) > 1 else legal[0]
    return rng.choice(legal)


def _play(client, state: dict, game_id: str, rng: random.Random, until) -> dict:
    while state["phase"] != "game_over" and not until(state):
        state = client.post(
            f"/api/games/{game_id}/actions", json={"action": _choose(state, rng)}
        ).json()
    return state


# --- /api/rules -------------------------------------------------------------------------------


def test_rules_list_the_death_star_numbers_and_whether_they_apply(client):
    on = client.get("/api/rules").json()
    assert on["deathStarRules"] is True
    numbers = on["deathStar"]
    off = rules_to_json(CLASSIC_CONFIG)
    assert off["deathStarRules"] is False
    assert set(off["deathStar"]) == set(numbers)
    assert numbers["fleetLimit"] == RULES_ON.fleet_limit
    assert [t["price"] for t in numbers["fleetTiers"]] == [t.price for t in RULES_ON.fleet_tiers]
    assert numbers["fleetTiers"][-1]["count"] == "unlimited"
    assert [s["value"] for s in numbers["stages"]] == list(RULES_ON.death_star_stage_values)
    assert [s["result"] for s in numbers["stages"]] == list(RULES_ON.death_star_stage_results)
    assert numbers["stages"][0]["name"] == "Frame"
    assert numbers["cubesPerStage"] == RULES_ON.death_star_cubes_per_stage
    assert numbers["backstopRounds"] == RULES_ON.death_star_backstop_rounds
    assert numbers["siteTag"] == RULES_ON.death_star_tag
    assert numbers["contractPartnerTags"] == sorted(RULES_ON.contract_partner_tags)


# --- session JSON -----------------------------------------------------------------------------


def test_rules_off_state_only_adds_fields(client, classic_rules):
    body = client.post("/api/games", json={"seats": SEATS, "seed": 4}).json()
    state = _play(
        client,
        body["state"],
        body["gameId"],
        random.Random(4),
        lambda s: (s["roundNumber"] >= 1 and s["phase"] == "dividend"),
    )
    assert set(state) == STATE_KEYS
    for corp in state["corporations"]:
        assert set(corp) == CORPORATION_KEYS
        for pair in corp["revenue"]["pairs"]:
            assert pair["contract"] is False
    assert all("deathStar" not in move["after"] for move in state["moves"])
    assert state["totalRounds"] == CLASSIC_CONFIG.total_rounds


def test_new_rules_on_game_shows_the_track_and_both_sites(client):
    state = client.post("/api/games", json={"seats": SEATS, "seed": 4}).json()["state"]
    track = state["deathStar"]
    assert [s["status"] for s in track["sites"]] == ["active", "reserved"]
    assert [s["region"] for s in track["sites"]] == list(RULES_ON.death_star_site_regions)
    assert track["siteName"] == "Death Star" and track["siteTag"] == "W"
    assert track["stage"] == 0 and track["cubes"] == 0
    assert track["contractValue"] == RULES_ON.death_star_stage_values[0]
    assert track["totalCubes"] == 4 * RULES_ON.death_star_cubes_per_stage
    assert not any(s["filled"] or s["resolved"] for s in track["stages"])
    assert track["finalRound"] == track["backstopRound"] == state["totalRounds"]
    assert track["fleets"]["price"] == RULES_ON.fleet_tiers[0].price
    assert track["fleets"]["tier"] == 0 and track["fleets"]["sold"] == 0
    assert track["fleets"]["limit"] == RULES_ON.fleet_limit
    assert all("fleetRevenue" in corp for corp in state["corporations"])


def test_fleet_step_through_the_api(client):
    body = client.post("/api/games", json={"seats": SEATS, "seed": 4}).json()
    game_id = body["gameId"]
    state = _play(
        client,
        body["state"],
        game_id,
        random.Random(4),
        lambda s: s["phase"] == "fleet" and s["waitingOnHuman"],
    )
    assert state["phase"] == "fleet"
    buy = next(a for a in state["legalActions"] if a["type"] == "buy_fleet")
    assert buy["cost"] == state["deathStar"]["fleets"]["price"]
    corp_id = state["currentCorporation"]
    corp = next(c for c in state["corporations"] if c["id"] == corp_id)
    assert corp["fleetRevenue"]["withNextFleet"] >= corp["revenue"]["total"]
    assert len(corp["revenue"]["pairs"]) <= corp["fleets"]
    after = client.post(f"/api/games/{game_id}/actions", json={"action": buy}).json()
    bought = next(c for c in after["corporations"] if c["id"] == corp_id)
    assert bought["fleets"] == corp["fleets"] + 1
    assert bought["treasury"] == corp["treasury"] - buy["cost"]
    assert after["deathStar"]["fleets"]["sold"] == state["deathStar"]["fleets"]["sold"] + 1
    (move,) = after["moves"]
    assert move["phase"] == "fleet" and move["action"] == buy
    assert move["after"]["deathStar"]["fleets"]["sold"] == after["deathStar"]["fleets"]["sold"]


def test_rules_on_game_replays_from_its_save(client, store, monkeypatch):
    body = client.post("/api/games", json={"seats": SEATS, "seed": 9}).json()
    game_id = body["gameId"]
    state = _play(client, body["state"], game_id, random.Random(9), lambda s: s["roundNumber"] >= 3)
    assert state["deathStar"]["cubes"] > 0
    assert any(c["fleets"] > 0 for c in state["corporations"])
    monkeypatch.setattr("bby18.api.saves.CODE_VERSION", "a-newer-engine")
    assert client.get(f"/api/games/{game_id}").json() == {**state, "moves": []}


# --- the track's later states -----------------------------------------------------------------


def _session() -> GameSession:
    seats = (Seat("Me", False), Seat("You", False))
    return GameSession(new_session(2, seats).game)


def test_site_move_vacates_the_first_site():
    session = _session()
    game = session.game
    game.death_star.cubes = 2 * RULES_ON.death_star_cubes_per_stage
    game.resolve_death_star()
    track = session_to_json(session)["deathStar"]
    assert [s["status"] for s in track["sites"]] == ["vacated", "active"]
    assert track["stage"] == 2
    assert track["contractValue"] == RULES_ON.death_star_stage_values[2]
    assert [s["resolved"] for s in track["stages"]] == [True, True, False, False]


def test_launch_ends_the_game_after_this_round():
    session = _session()
    game = session.game
    game.death_star.cubes = 4 * RULES_ON.death_star_cubes_per_stage
    game.resolve_death_star()
    state = session_to_json(session)
    track = state["deathStar"]
    assert track["launched"]
    assert [s["status"] for s in track["sites"]] == ["vacated", "launched"]
    assert track["contractValue"] == 0
    assert track["finalRound"] == state["totalRounds"] == game.round_number + 1
    assert track["stage"] == len(track["stages"])


def test_fleet_tiers_count_down_across_tiers():
    tiers = fleet_tiers_to_json(RULES_ON.fleet_tiers, 8)
    assert [t["remaining"] for t in tiers] == [0, 4, 6, "unlimited"]


def test_closed_corporation_is_listed_as_closed():
    session = _session()
    game = session.game
    corp = next(iter(game.corporations.values()))
    corp.status = CorpStatus.FLOATED
    corp.president = "P1"
    game.players[0].shares[corp.id] = 2
    game.close_bankrupt(corp)
    data = next(c for c in session_to_json(session)["corporations"] if c["id"] == corp.id)
    assert data["status"] == "closed"
    assert data["fleetRevenue"] == {"withNextFleet": 0, "uncapped": 0, "uncappedPairs": 0}
    assert corp.id not in session_to_json(session)["players"][0]["shares"]


def test_contract_pairs_are_marked(monkeypatch):
    session = _session()
    game = session.game
    corp = next(iter(game.corporations.values()))
    corp.status = CorpStatus.FLOATED
    corp.fleets = 2
    site = game.board.planet_named("Death Star")
    partner = next(p for p in game.board.planets if "R" in p.tags)
    other = next(p for p in game.board.planets if p not in (site, partner))
    contract = ScoredPair(site, partner, game.contract_value(), False, True)
    basic = ScoredPair(other, game.board.planet_named(corp.spec.homeworld), 10, False)
    monkeypatch.setattr(game, "revenue", lambda c: RevenueResult((contract, basic)))
    data = next(c for c in session_to_json(session)["corporations"] if c["id"] == corp.id)
    assert [p["contract"] for p in data["revenue"]["pairs"]] == [True, False]
