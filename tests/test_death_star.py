"""The Death Star and fleets rules (``death_star_rules``, adopted 2026-10-26)."""

import hashlib
import random
from dataclasses import replace
from itertools import combinations

import pytest

from bby18.actions import BuyFleet, BuyShare, FinishFleets, NoNetworkAction, PassStock, ShareSource
from bby18.api.serialize import action_to_json, match_action, session_to_json
from bby18.board import Planet, Terrain, load_board
from bby18.bots import GreedyBot, GreedyPolicy, RandomBot
from bby18.config import (
    CLASSIC_CONFIG,
    DEFAULT_CONFIG,
    FLEET_CONFIG,
    FOUR_CORPORATIONS,
    UNLIMITED,
    FleetTier,
)
from bby18.death_star import SITE_NAME, SitePlacementError, place_sites
from bby18.game import Game
from bby18.hexgrid import Hex
from bby18.network import IllegalAction
from bby18.playtest import play_one
from bby18.revenue import (
    RevenueResult,
    ScoredPair,
    compute_revenue,
    compute_revenue_uncached,
)
from bby18.runner import run_game
from bby18.session import Dividend, GameSession, Phase
from bby18.state import NO_PLAYER, CorpStatus
from bby18.terrain import generate_terrain

RULES = replace(CLASSIC_CONFIG, death_star_rules=True)
"""The Death Star rules with the numbers they were built and tested with (6 cubes per stage,
sites anywhere that qualifies). ``CLASSIC_CONFIG`` adopted tighter numbers on 2026-10-26; these
tests pin the mechanics, not the adopted numbers."""
OPEN_RULES = replace(RULES, asteroid_fraction=0.0, nebula_fraction=0.0)
"""Tests that build specific tiles run on an empty sky."""


def new_game(config=RULES, seed=1, players=3):
    return Game.new([f"Player {i + 1}" for i in range(players)], config, seed)


def float_corp(game, corp_id, par=60):
    p1, p2, p3 = game.players[:3]
    for player, extra in ((p1, par), (p2, 0), (p3, 0), (p2, 0)):
        game.apply_stock_action(player, BuyShare(corp_id, ShareSource.IPO, extra), set())
    corp = game.corp(corp_id)
    assert corp.floated
    return corp


def planet(name, tags, region="Mid Rim", hex=Hex(0, 0)):
    return Planet(name, hex, region, frozenset(tags.split("/")))


def contract_pair(value=40):
    site = planet(SITE_NAME, "W", hex=Hex(1, 0))
    return ScoredPair(planet("Kessel", "R", hex=Hex(2, 0)), site, value, False, True)


def log_texts(game, start=0):
    return [str(e) for e in game.log[start:]]


# --- capped matching ------------------------------------------------------------------------


def _brute_force(planets, config, contract_value, max_pairs):
    """Best total over every matching with at most ``max_pairs`` pairs."""
    values = {}
    for a, b in combinations(planets, 2):
        values[a.name, b.name] = compute_revenue_uncached(
            [a, b], config, contract_value=contract_value
        ).pair_total

    def best(remaining, pairs_left):
        if pairs_left == 0 or len(remaining) < 2:
            return 0
        first, rest = remaining[0], remaining[1:]
        result = best(rest, pairs_left)  # first stays unpaired
        for i, other in enumerate(rest):
            value = values[first.name, other.name]
            result = max(result, value + best(rest[:i] + rest[i + 1 :], pairs_left - 1))
        return result

    return best(list(planets), max_pairs)


def test_capped_matching_equals_brute_force_for_every_cap():
    rng = random.Random(7)
    tags = ["A", "M", "R", "I", "S", "R/I", "A/M"]
    regions = ["Core", "Mid Rim", "Outer Rim"]
    for trial in range(60):
        n = rng.randint(0, 9)
        planets = [
            planet(f"p{i}", rng.choice(tags), rng.choice(regions), Hex(i, trial % 3))
            for i in range(n)
        ]
        if n and rng.random() < 0.6:
            planets[0] = planet(SITE_NAME, "W", rng.choice(regions), Hex(0, trial % 3))
        contract_value = rng.choice([0, 40, 70])
        for cap in range(0, n // 2 + 2):
            result = compute_revenue_uncached(
                planets, RULES, contract_value=contract_value, max_pairs=cap
            )
            assert len(result.pairs) <= cap
            used = [p.name for pair in result.pairs for p in (pair.a, pair.b)]
            assert len(used) == len(set(used))
            assert result.pair_total == _brute_force(planets, RULES, contract_value, cap)


def test_uncapped_matching_is_unchanged_by_a_large_cap():
    planets = [planet(f"p{i}", t, hex=Hex(i, 0)) for i, t in enumerate("AMRISIM")]
    assert compute_revenue(planets, RULES, max_pairs=3) == compute_revenue(planets, RULES)
    assert compute_revenue(planets, RULES, max_pairs=0).pairs == ()


def test_cap_and_contract_value_are_part_of_the_memo_key():
    planets = [planet(SITE_NAME, "W", hex=Hex(0, 0))] + [
        planet(f"p{i}", t, hex=Hex(i + 1, 0)) for i, t in enumerate("RAMIS")
    ]
    one = compute_revenue(planets, RULES, contract_value=40, max_pairs=1)
    two = compute_revenue(planets, RULES, contract_value=40, max_pairs=2)
    dearer = compute_revenue(planets, RULES, contract_value=70, max_pairs=1)
    assert one.total == 40 and len(one.pairs) == 1
    assert two.total == 70 and len(two.pairs) == 2
    assert dearer.total == 70 and dearer.contract_pairs == 1


# --- contract pairs -----------------------------------------------------------------------


def test_contract_pair_scores_the_stage_value_without_the_regional_bonus():
    site = planet(SITE_NAME, "W", "Outer Rim", Hex(0, 0))
    core_resources = planet("Core R", "R", "Core", Hex(1, 0))
    result = compute_revenue([site, core_resources], RULES, contract_value=50)
    (pair,) = result.pairs
    assert pair.contract and not pair.typed
    assert pair.value == 50
    assert result.contract_pairs == 1
    assert "contract 50" in str(pair)


def test_site_with_a_non_partner_planet_is_a_basic_route():
    site = planet(SITE_NAME, "W", hex=Hex(0, 0))
    farm = planet("Farm", "A", hex=Hex(1, 0))
    result = compute_revenue([site, farm], RULES, contract_value=50)
    assert result.total == RULES.basic_route_value
    assert result.contract_pairs == 0


def test_contract_value_follows_the_stage_being_built():
    game = new_game()
    values = []
    for resolved in range(4):
        game.death_star.stages_resolved = resolved
        values.append(game.contract_value())
    assert values == [40, 50, 60, 70]
    game.death_star.launched = True
    assert game.contract_value() == 0


def test_revenue_uses_at_most_one_pair_per_fleet():
    game = new_game()
    cec = float_corp(game, "CEC")
    planets = [planet(f"p{i}", t, hex=Hex(i, 0)) for i, t in enumerate("AMRSIM")]
    game.reachable_planets = lambda corp: planets  # type: ignore[method-assign]
    totals = []
    for fleets in range(4):
        cec.fleets = fleets
        result = game.revenue(cec)
        assert len(result.pairs) == fleets
        totals.append(result.total)
    assert totals == [0, 30, 60, 90]


def test_revenue_is_uncapped_with_the_rules_off():
    game = new_game(CLASSIC_CONFIG)
    cec = float_corp(game, "CEC")
    planets = [planet(f"p{i}", t, hex=Hex(i, 0)) for i, t in enumerate("AMRSIM")]
    game.reachable_planets = lambda corp: planets  # type: ignore[method-assign]
    assert cec.fleets == 0
    assert len(game.revenue(cec).pairs) == 3


# --- fleets ----------------------------------------------------------------------------------


def test_fleet_price_rises_within_one_purchase_step():
    game = new_game()
    cec = float_corp(game, "CEC")
    game.fleets_sold = 5
    assert game.legal_fleet_actions(cec) == [BuyFleet(60)]
    start = len(game.log)
    game.apply_fleet_action(cec, BuyFleet(60))
    assert game.fleet_price() == 90 and game.fleet_tier() == 1
    assert game.legal_fleet_actions(cec) == [BuyFleet(90), FinishFleets()]
    game.apply_fleet_action(cec, BuyFleet(90))
    assert cec.fleets == 2
    assert cec.treasury == 480 - 60 - 90
    assert any("fleet price rises to 90" in t for t in log_texts(game, start))


def test_last_fleet_tier_never_sells_out():
    game = new_game()
    game.fleets_sold = 1000
    assert game.fleet_price() == 160
    assert game.fleet_tier() == 3


def test_buying_at_a_stale_price_is_illegal():
    game = new_game()
    cec = float_corp(game, "CEC")
    game.fleets_sold = 6
    with pytest.raises(IllegalAction):
        game.apply_fleet_action(cec, BuyFleet(60))


def test_fleet_limit():
    game = new_game()
    cec = float_corp(game, "CEC")
    cec.fleets = RULES.fleet_limit
    assert game.legal_fleet_actions(cec) == [FinishFleets()]
    with pytest.raises(IllegalAction):
        game.apply_fleet_action(cec, BuyFleet(game.fleet_price()))


def test_first_fleet_is_mandatory():
    game = new_game()
    cec = float_corp(game, "CEC")
    assert game.legal_fleet_actions(cec) == [BuyFleet(60)]
    with pytest.raises(IllegalAction):
        game.apply_fleet_action(cec, FinishFleets())


def test_fleets_do_not_exist_with_the_rules_off():
    game = new_game(CLASSIC_CONFIG)
    cec = float_corp(game, "CEC")
    with pytest.raises(IllegalAction):
        game.legal_fleet_actions(cec)
    assert not game.must_close(cec)


def test_session_runs_a_fleet_step_between_network_and_dividend():
    game = new_game()
    float_corp(game, "CEC")
    session = GameSession(game)
    for _ in game.players:
        session.apply(PassStock())
    assert session.phase is Phase.NETWORK
    session.apply(NoNetworkAction())
    assert session.phase is Phase.FLEET
    assert session.current_corporation.id == "CEC"
    assert session.legal_actions() == [BuyFleet(60)]
    session.apply(BuyFleet(60))
    assert session.phase is Phase.FLEET
    session.apply(FinishFleets())
    assert session.phase is Phase.DIVIDEND


# --- bankruptcy ----------------------------------------------------------------------------


def test_bankruptcy_closes_the_corporation_for_good():
    game = new_game(OPEN_RULES)
    cec = float_corp(game, "CEC")
    float_corp(game, "KDY")
    holders = {p.id: p.shares_in("CEC") for p in game.players}
    assert sum(holders.values()) == 5
    certificates = {p.id: game.certificate_count(p) for p in game.players}
    worth = {p.id: game.player_worth(p) for p in game.players}
    home = game.homeworld(cec)
    tile_hex, exits = next(
        (n, frozenset({n.direction_to(home), d}))
        for _, n in game.board.neighbors(home)
        if not game.board.is_planet(n)
        for d in sorted(game.network.legal_exits(n))
        if d != n.direction_to(home)
    )
    game.network.chart("CEC", tile_hex, exits, game.reachable(cec))
    game.network.extend_service("KDY", tile_hex, frozenset({home}))
    cec.treasury = 50
    bank_before = game.bank
    assert game.must_close(cec)

    game.close_bankrupt(cec)

    assert cec.status is CorpStatus.CLOSED and not cec.floated
    assert all(p.shares_in("CEC") == 0 for p in game.players)
    for p in game.players:
        assert game.player_worth(p) == worth[p.id] - holders[p.id] * game.price(cec)
        lost = holders[p.id] - (1 if p.id == "P1" else 0) if holders[p.id] else 0
        assert game.certificate_count(p) == certificates[p.id] - lost
    assert cec.ipo_shares == 0 and cec.pool_shares == 0 and cec.treasury == 0
    assert cec.president == NO_PLAYER
    assert game.bank == bank_before + 50
    assert game.network.is_charted(tile_hex)
    assert game.network.service_of("CEC") == frozenset()
    assert "KDY" in game.network.corporations_serving(tile_hex)
    assert [c.id for c in game.operating_order()] == ["KDY"]
    assert game.closed_corporations() == [cec]
    for player in game.players:
        actions = game.legal_stock_actions(player, set())
        assert not any(getattr(a, "corp_id", "") == "CEC" for a in actions)
    with pytest.raises(IllegalAction):
        game.apply_stock_action(game.players[1], BuyShare("CEC", ShareSource.IPO), set())
    start = len(game.log)
    game.finish_stock_round()
    assert not any("CEC is sold out" in t for t in log_texts(game, start))


def test_corporation_with_a_fleet_or_the_cash_for_one_is_not_bankrupt():
    game = new_game()
    cec = float_corp(game, "CEC")
    cec.treasury = 60
    assert not game.must_close(cec)
    cec.treasury = 0
    cec.fleets = 1
    assert not game.must_close(cec)
    with pytest.raises(IllegalAction):
        game.close_bankrupt(cec)


def test_session_closes_a_bankrupt_corporation_at_its_fleet_step():
    game = new_game()
    cec = float_corp(game, "CEC")
    kdy = float_corp(game, "KDY")
    session = GameSession(game)
    for _ in game.players:
        session.apply(PassStock())
    assert session.operating_queue == ["CEC", "KDY"]
    cec.treasury = 59
    session.apply(NoNetworkAction())
    assert cec.status is CorpStatus.CLOSED
    assert session.phase is Phase.NETWORK
    assert session.current_corporation is kdy
    assert any("CEC: is bankrupt" in t for t in log_texts(game))


# --- the Death Star track -------------------------------------------------------------------


def test_empire_adds_a_cube_every_stock_round():
    game = new_game()
    game.finish_stock_round()
    game.finish_stock_round()
    assert game.death_star.cubes == 2
    assert "Empire: adds 1 cube" in log_texts(game)[-1]


def test_no_cubes_with_the_rules_off():
    game = new_game(CLASSIC_CONFIG)
    start = len(game.log)
    game.finish_stock_round()
    assert game.death_star.cubes == 0
    assert log_texts(game, start) == []


@pytest.mark.parametrize("pay", [True, False])
def test_each_contract_pair_scored_adds_a_cube_paid_or_withheld(pay):
    game = new_game()
    cec = float_corp(game, "CEC")
    cec.fleets = 2
    pairs = (contract_pair(), contract_pair())
    game.revenue = lambda corp: RevenueResult(pairs)  # type: ignore[method-assign]
    game.settle_revenue(cec, pay=pay)
    assert game.death_star.cubes == 2


def test_stage_overflow_carries_cubes_and_waits_for_the_end_of_the_round():
    game = new_game()
    cec = float_corp(game, "CEC")
    cec.fleets = 1
    game.death_star.cubes = 4
    pairs = (contract_pair(), contract_pair(), contract_pair())
    game.revenue = lambda corp: RevenueResult(pairs)  # type: ignore[method-assign]
    game.settle_revenue(cec, pay=True)
    assert game.death_star.cubes == 7
    assert game.death_star.stages_filled(RULES) == 1
    assert any("stage 1 (Frame) is built" in t for t in log_texts(game))
    assert cec.fleets == 1, "the seizure waits for the end of the round"
    game.resolve_death_star()
    assert cec.fleets == 0
    assert game.death_star_stage() == 1
    assert game.contract_value() == 50


def test_seizure_takes_one_fleet_from_every_corporation_that_has_one():
    game = new_game()
    cec, kdy, csc = (float_corp(game, c) for c in ("CEC", "KDY", "CSC"))
    cec.fleets, kdy.fleets, csc.fleets = 2, 1, 0
    sold, price = game.fleets_sold, game.fleet_price()
    game.death_star.cubes = 5
    game.finish_stock_round()
    game.resolve_death_star()
    assert (cec.fleets, kdy.fleets, csc.fleets) == (1, 0, 0)
    assert (game.fleets_sold, game.fleet_price()) == (sold, price), "seized fleets leave the game"
    seizures = [t for t in log_texts(game) if "Empire: seizes" in t]
    assert seizures == [
        "[setup] Empire: seizes a fleet from CEC; it owns 1",
        "[setup] Empire: seizes a fleet from KDY; it owns 0",
    ]


def test_two_stages_filling_together_apply_in_order():
    game = new_game()
    cec = float_corp(game, "CEC")
    cec.fleets = 2
    first, second = game.death_star.sites
    game.death_star.cubes = 11
    game.finish_stock_round()
    start = len(game.log)
    game.resolve_death_star()
    texts = log_texts(game, start)
    assert "seizes a fleet from CEC" in texts[0]
    assert "moves the Death Star site" in texts[1]
    assert cec.fleets == 1
    assert game.death_star_site() == second
    assert game.death_star_reserved_sites() == ()
    assert game.board.planet_named(SITE_NAME).hex == second
    assert not game.board.is_planet(first)
    assert game.contract_value() == 60


def _line_through(game, site):
    """Two hexes on opposite sides of ``site``, neither a planet, with the directions from each
    toward the site."""
    board = game.board
    for _, a in board.neighbors(site):
        to_site_a = a.direction_to(site)
        b = site.neighbor(to_site_a)
        if board.contains(b) and not board.is_planet(a) and not board.is_planet(b):
            return a, to_site_a, b, to_site_a.opposite
    raise AssertionError(f"No straight line through {site}")


def _chart_toward(game, corp_id, hex, toward, reach):
    other = min(d for d in game.network.legal_exits(hex) if d != toward)
    game.network.chart(corp_id, hex, frozenset({toward, other}), reach)


def test_site_move_cuts_a_network_that_ran_through_it():
    game = new_game(OPEN_RULES)
    site, future = game.death_star.sites
    a, a_to_site, b, b_to_site = _line_through(game, site)
    _chart_toward(game, "CEC", a, a_to_site, frozenset({site}))
    _chart_toward(game, "CEC", b, b_to_site, frozenset({site}))
    assert {site, b} <= game.network.reachable("CEC", a)

    game.death_star.cubes = 12
    game.resolve_death_star()

    assert game.network.board is game.board
    assert not game.board.is_planet(site)
    assert game.network.is_charted(a) and game.network.is_charted(b), "tiles stay"
    assert game.network.reachable("CEC", a) == frozenset({a})
    assert game.board.is_planet(future)
    # The old site is plain uncharted space now, so it can be charted.
    game.network.check_chart(
        "CEC", site, frozenset({a_to_site.opposite, b_to_site.opposite}), frozenset({a})
    )
    # What-if copies see the same board.
    assert game.network.copy().board is game.board


def test_reserved_site_cannot_be_charted_but_tiles_may_face_it():
    for seed in range(1, 40):
        game = new_game(OPEN_RULES, seed=seed)
        _, future = game.death_star.sites
        board = game.board
        approach = [
            (n, p)
            for _, n in board.neighbors(future)
            if not board.is_planet(n)
            for _, p in board.neighbors(n)
            if board.is_planet(p) and p != future
        ]
        if approach:
            break
    else:
        pytest.fail("No seed puts the future site two steps from a planet")
    neighbor, home = approach[0]
    toward_neighbor = future.direction_to(neighbor)
    other = min(game.network.legal_exits(future) - {toward_neighbor})
    with pytest.raises(IllegalAction, match="reserved"):
        game.network.check_chart(
            "CEC", future, frozenset({toward_neighbor, other}), frozenset(board.hexes)
        )
    exits = frozenset({neighbor.direction_to(home), neighbor.direction_to(future)})
    game.network.chart("CEC", neighbor, exits, frozenset({home}))
    assert future not in game.network.reachable("CEC", home)
    game.death_star.cubes = 12
    game.resolve_death_star()
    assert future in game.network.reachable("CEC", home)


def test_launch_removes_the_site_and_sets_the_last_round():
    game = new_game()
    site, future = game.death_star.sites
    game.round_number = 3
    game.death_star.cubes = 24
    game.resolve_death_star()
    assert game.death_star.launched
    assert game.death_star_site() is None
    assert not game.board.is_planet(site) and not game.board.is_planet(future)
    assert game.contract_value() == 0
    assert game.round_limit() == 4
    assert not game.is_over()
    game.round_number = 4
    assert game.is_over()
    assert any("launches the Death Star" in t for t in log_texts(game))


# --- game end ------------------------------------------------------------------------------


def _drive(session, bot, until):
    """Play every seat with ``bot`` until ``until(session)`` or the game ends."""
    game = session.game
    while session.phase is not Phase.GAME_OVER and not until(session):
        legal = session.legal_actions()
        if session.phase is Phase.STOCK:
            action = bot.choose_stock_action(game, session.current_player, legal)
        elif session.phase is Phase.NETWORK:
            action = bot.choose_network_action(game, session.current_corporation, legal)
        elif session.phase is Phase.FLEET:
            action = bot.choose_fleet_action(game, session.current_corporation, legal)
        else:
            action = Dividend.PAY if Dividend.PAY in legal else Dividend.WITHHOLD
        session.apply(action)


def test_game_ends_after_the_set_of_operating_rounds_in_which_the_station_launches():
    game = new_game()
    session = GameSession(game)
    bot = GreedyBot(random.Random(3))
    _drive(session, bot, lambda s: s.game.round_label == "OR2.1")
    assert session.phase is Phase.NETWORK
    game.death_star.cubes = 24
    _drive(session, bot, lambda s: s.game.round_label == "OR2.2")
    assert game.death_star.launched, "the stages resolve at the end of OR2.1"
    assert not game.is_over()
    _drive(session, bot, lambda s: False)
    assert session.phase is Phase.GAME_OVER
    assert game.round_number == 2
    labels = {e.round_label for e in game.log}
    assert "OR2.2" in labels and "SR3" not in labels


def test_backstop_ends_a_game_whose_station_never_launches():
    config = replace(RULES, death_star_cubes_per_stage=1000, death_star_backstop_rounds=3)
    game, _ = play_one(2, 3, "greedy-path", config)
    assert game.is_over()
    assert game.round_number == 3
    labels = {e.round_label for e in game.log}
    assert "OR3.2" in labels and "SR4" not in labels


def test_default_backstop_is_eight_rounds():
    config = replace(RULES, death_star_cubes_per_stage=1000)
    game, _ = play_one(1, 3, "greedy", config)
    assert game.round_number == 8


# --- site placement --------------------------------------------------------------------------


def test_site_placement_is_seeded_and_satisfies_its_constraints():
    homeworlds = [c.homeworld for c in RULES.corporations]
    for seed in range(150):
        board = load_board(RULES.map_file)
        board = board.with_terrain(generate_terrain(board, seed, RULES))
        sites = place_sites(board, seed, RULES)
        assert sites == place_sites(board, seed, RULES)
        first, second = sites
        assert first != second
        for site, region, other in ((first, "Outer Rim", second), (second, "Mid Rim", first)):
            assert board.region_of(site) == region
            assert not board.is_planet(site)
            assert board.terrain_at(site) is Terrain.SPACE
            for name in homeworlds:
                assert site.distance(board.planet_named(name).hex) >= 3
            chartable = [
                n for _, n in board.neighbors(site) if not board.is_planet(n) and n != other
            ]
            assert len(chartable) >= 2


def test_game_places_the_first_site_as_a_planet_and_leaves_terrain_alone():
    on, off = new_game(RULES, seed=5), new_game(CLASSIC_CONFIG, seed=5)
    assert on.board.terrain == off.board.terrain
    first, second = on.death_star.sites
    site = on.board.planet_named(SITE_NAME)
    assert site.hex == first and site.tags == frozenset({"W"}) and site.region == "Outer Rim"
    assert on.network.reserved == frozenset({second})
    assert on.death_star_reserved_sites() == (second,)
    assert len(on.board.planets) == len(off.board.planets) + 1
    assert off.death_star_site() is None and off.network.reserved == frozenset()
    assert "begins the Death Star" in str(on.log[0])
    assert off.log == []


def test_site_placement_raises_when_no_hex_qualifies():
    board = load_board(RULES.map_file)
    with pytest.raises(SitePlacementError):
        place_sites(board, 1, replace(RULES, death_star_min_homeworld_distance=50))


def test_region_of_a_space_hex_is_its_nearest_planets_with_core_winning_ties():
    board = load_board(RULES.map_file)
    for hex in board.space_hexes():
        nearest = min(p.hex.distance(hex) for p in board.planets)
        regions = {p.region for p in board.planets if p.hex.distance(hex) == nearest}
        expected = next(r for r in ("Core", "Mid Rim", "Outer Rim") if r in regions)
        assert board.region_of(hex) == expected


# --- config ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"fleet_tiers": (FleetTier(6, 60),)},
        {"fleet_tiers": (FleetTier(UNLIMITED, 60), FleetTier(UNLIMITED, 90))},
        {"fleet_tiers": (FleetTier(0, 60), FleetTier(UNLIMITED, 90))},
        {"fleet_tiers": ()},
        {"fleet_limit": 0},
        {"death_star_stage_values": (40, 50, 60)},
        {"death_star_stage_results": ("seizure", "move", "completion", "seizure")},
        {"death_star_stage_results": ("seizure", "seizure", "seizure", "completion")},
        {"death_star_stage_results": ("seizure", "move", "explode", "completion")},
        {"death_star_cubes_per_stage": 0},
        {"death_star_backstop_rounds": 0},
        {"death_star_site_regions": ("Outer Rim",)},
        {"contract_partner_tags": frozenset({"W"})},
    ],
)
def test_bad_death_star_numbers_are_rejected(overrides):
    with pytest.raises(ValueError):
        replace(RULES, **overrides).validate_rule_variants()


def test_default_death_star_numbers_match_the_decisions_doc():
    config = DEFAULT_CONFIG
    assert config.death_star_rules and config.facility_rules
    assert config.fleet_tiers == (
        FleetTier(6, 60),
        FleetTier(6, 90),
        FleetTier(6, 120),
        FleetTier(UNLIMITED, 160),
    )
    assert config.fleet_limit == 3
    assert config.planet_base_exits == 1
    assert config.facilities_per_planet == 2
    assert config.death_star_stage_values == (50, 60, 70, 80)
    assert config.death_star_stage_results == ("seizure", "move", "seizure", "completion")
    assert config.death_star_cubes_per_stage == 5
    assert config.death_star_max_homeworld_distance == 4
    assert config.death_star_near_homeworlds == 2
    assert config.empire_cubes_per_stock_round == 1
    assert config.death_star_backstop_rounds == 8


def test_fleet_config_is_the_default_before_the_facilities_were_adopted():
    assert FLEET_CONFIG == replace(
        DEFAULT_CONFIG,
        corporations=FOUR_CORPORATIONS,
        planet_pair_bonus={},
        facility_rules=False,
        fleet_limit=4,
        death_star_stage_values=(40, 50, 60, 70),
    )
    FLEET_CONFIG.validate_rule_variants()


def test_classic_config_is_the_fleet_config_before_the_death_star_was_adopted():
    assert CLASSIC_CONFIG == replace(
        FLEET_CONFIG,
        map_file="map-127.json",
        death_star_rules=False,
        death_star_cubes_per_stage=6,
        death_star_max_homeworld_distance=99,
        death_star_near_homeworlds=1,
    )
    assert RULES.death_star_rules and RULES.death_star_cubes_per_stage == 6


def test_adopted_sites_are_contested_on_most_seeds():
    """Within 4 hexes of two homeworlds, relaxed hex by hex on a seed that has no such hex."""
    board = load_board(DEFAULT_CONFIG.map_file)
    homeworlds = [board.planet_named(c.homeworld).hex for c in DEFAULT_CONFIG.corporations]
    contested = 0
    for seed in range(1, 41):
        for site in new_game(DEFAULT_CONFIG, seed=seed).death_star.sites:
            contested += sum(1 for h in homeworlds if site.distance(h) <= 4) >= 2
    assert contested >= 60


# --- whole games ---------------------------------------------------------------------------


BOTS = {
    "greedy": lambda rng: GreedyBot(rng),
    "greedy-path": lambda rng: GreedyBot(rng, GreedyPolicy(routing="path")),
    "random": RandomBot,
}


@pytest.mark.parametrize("players", [2, 3, 4])
@pytest.mark.parametrize("kind", sorted(BOTS))
@pytest.mark.parametrize("seed", [1, 2])
def test_bot_games_with_death_star_rules_complete_and_conserve_money(players, kind, seed):
    game = new_game(RULES, seed=seed, players=players)
    rng = random.Random(seed)
    run_game(game, {p.id: BOTS[kind](random.Random(rng.random())) for p in game.players})
    assert game.is_over()
    assert game.round_number <= RULES.death_star_backstop_rounds
    player_cash = sum(p.cash for p in game.players)
    corp_cash = sum(c.treasury for c in game.corporations.values())
    assert player_cash + corp_cash + game.bank == players * RULES.starting_cash(players)
    for corp in game.corporations.values():
        assert 0 <= corp.fleets <= RULES.fleet_limit
        if corp.status is CorpStatus.CLOSED:
            assert all(p.shares_in(corp.id) == 0 for p in game.players)


def test_many_greedy_games_with_death_star_rules_complete():
    for seed in range(3, 13):
        game, _ = play_one(seed, 3, "greedy-path", RULES)
        assert game.is_over()


# --- the standard rules are untouched ------------------------------------------------------

BASELINE_DIGESTS = {
    ("greedy", 3, 1): "f88e28baca45e17c",
    ("greedy-path", 3, 2): "728386dd8e6861a8",
    ("random", 4, 3): "6f945e6237ad5699",
    ("baron~0.5", 2, 4): "14a288032fc5917e",
    ("random", 3, 5): "7d0fbf376acf3b05",
    ("greedy-path", 4, 6): "328846ce8b3f5c4d",
}
"""Hashes of full game logs and final cash and worth, captured on the engine before the Death
Star rules were added."""


@pytest.mark.parametrize("key", sorted(BASELINE_DIGESTS))
def test_games_with_the_rules_off_play_exactly_as_before(key):
    kind, players, seed = key
    game, _ = play_one(seed, players, kind, CLASSIC_CONFIG)
    digest = hashlib.sha256()
    for entry in game.log:
        digest.update(str(entry).encode())
        digest.update(b"\n")
    for p in game.players:
        digest.update(f"{p.id}:{p.cash}:{game.player_worth(p)}\n".encode())
    assert digest.hexdigest()[:16] == BASELINE_DIGESTS[key]


FLEET_DIGESTS = {
    ("baron", 3, 1): "e20b33cd60fafa09",
    ("admiral", 3, 2): "ba7afe0ae7c8ab47",
    ("contractor", 4, 3): "8465908b0b06ecff",
    ("early-builder~0.5", 2, 4): "2d4120317fb9931b",
    ("random", 3, 5): "9eb4c26ff19ec0bb",
    ("greedy-path", 4, 6): "435ae7d47bcb6726",
    ("mix:staller,targeted,saver", 3, 7): "b9a344858f98111a",
}
"""Hashes of full game logs and final cash and worth under the fleet rules, captured on the
engine before the facility rules were added (main at 6d434e8, where they were the default)."""


@pytest.mark.parametrize("key", sorted(FLEET_DIGESTS))
def test_fleet_games_play_exactly_as_before_facilities(key):
    kind, players, seed = key
    game, _ = play_one(seed, players, kind, FLEET_CONFIG)
    digest = hashlib.sha256()
    for entry in game.log:
        digest.update(str(entry).encode())
        digest.update(b"\n")
    for p in game.players:
        digest.update(f"{p.id}:{p.cash}:{game.player_worth(p)}\n".encode())
    assert digest.hexdigest()[:16] == FLEET_DIGESTS[key]


# --- serialization -------------------------------------------------------------------------


def _bot_session(seed):
    game = new_game(RULES, seed=seed)
    rng = random.Random(seed)
    bots = {p.id: GreedyBot(random.Random(rng.random())) for p in game.players[1:]}
    return GameSession(game, bots, auto_forced=True)


def test_death_star_session_round_trips_through_submitted_actions():
    seed = 4
    session = _bot_session(seed)
    session.run_bots()
    human = GreedyBot(random.Random(99))
    submitted = []
    saw_fleet_state = False
    while session.phase is not Phase.GAME_OVER:
        assert session.waiting_on_human()
        game = session.game
        legal = session.legal_actions()
        if session.phase is Phase.STOCK:
            action = human.choose_stock_action(game, session.current_player, legal)
        elif session.phase is Phase.NETWORK:
            action = human.choose_network_action(game, session.current_corporation, legal)
        elif session.phase is Phase.FLEET:
            state = session_to_json(session)
            assert state["phase"] == "fleet"
            assert state["currentCorporation"] == session.current_corporation.id
            types = {a["type"] for a in state["legalActions"]}
            assert types <= {"buy_fleet", "finish_fleets"} and types
            saw_fleet_state = True
            action = human.choose_fleet_action(game, session.current_corporation, legal)
        else:
            action = Dividend.PAY if Dividend.PAY in legal else Dividend.WITHHOLD
        submitted.append(action_to_json(action))
        session.apply(action)
    assert saw_fleet_state
    assert any(a["type"] == "buy_fleet" for a in submitted)

    replayed = _bot_session(seed)
    replayed.run_bots()
    for data in submitted:
        replayed.apply(match_action(replayed.legal_actions(), data))
    assert log_texts(replayed.game) == log_texts(session.game)
    assert replayed.phase is Phase.GAME_OVER


def _site_next_to_a_planet(config):
    """A game whose first site is adjacent to a planet, with that planet's hex."""
    for seed in range(1, 200):
        game = new_game(config, seed=seed)
        site = game.death_star_site()
        for _, n in game.board.neighbors(site):
            if game.board.is_planet(n) and game.board.planet_at(n).name != SITE_NAME:
                return game, site, n
    raise AssertionError("No seed puts the first site next to a planet")


def test_a_planet_next_to_the_site_does_not_connect_without_a_lane():
    game, site, planet = _site_next_to_a_planet(OPEN_RULES)
    assert not game.network.connected(planet, site)
    assert site not in game.network.reachable("CEC", planet)


def test_a_charted_lane_connects_a_planet_to_an_adjacent_site():
    game, site, planet = _site_next_to_a_planet(OPEN_RULES)
    board = game.board
    lane = next(
        n
        for _, n in board.neighbors(planet)
        if n in {h for _, h in board.neighbors(site)} and not board.is_planet(n)
    )
    exits = frozenset({lane.direction_to(planet), lane.direction_to(site)})
    game.network.chart("CEC", lane, exits, frozenset({planet}))
    assert {lane, site} <= game.network.reachable("CEC", planet)


def test_contested_sites_lie_within_reach_of_two_homeworlds():
    config = replace(RULES, death_star_max_homeworld_distance=6, death_star_near_homeworlds=2)
    board = load_board(config.map_file)
    homeworlds = [board.planet_named(c.homeworld).hex for c in config.corporations]
    for seed in range(1, 40):
        game = new_game(config, seed=seed)
        for site in game.death_star.sites:
            near = [h for h in homeworlds if site.distance(h) <= 6]
            assert len(near) >= 2


def test_a_tight_contest_distance_relaxes_rather_than_failing():
    config = replace(RULES, death_star_max_homeworld_distance=3, death_star_near_homeworlds=2)
    for seed in range(1, 40):
        first, second = new_game(config, seed=seed).death_star.sites
        assert first != second


def test_contest_distance_needs_enough_corporations():
    with pytest.raises(ValueError, match="death_star_near_homeworlds"):
        replace(RULES, death_star_near_homeworlds=5).validate_rule_variants()
