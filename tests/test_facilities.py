"""Facilities and planet exits (``facility_rules``, experimental since 2026-10-26)."""

from dataclasses import replace

import pytest

from bby18.actions import (
    BuildFacility,
    BuyFleet,
    BuyShare,
    Chart,
    FinishFleets,
    NoNetworkAction,
    PassStock,
    ShareSource,
    Upgrade,
)
from bby18.board import Planet, load_board
from bby18.config import CLASSIC_CONFIG, SEIZURE, GameConfig
from bby18.death_star import SITE_NAME
from bby18.game import EMPIRE, Game
from bby18.hexgrid import Direction as D
from bby18.hexgrid import Hex
from bby18.network import HyperspaceNetwork, IllegalAction
from bby18.playtest import play_one
from bby18.session import GameSession, Phase
from bby18.state import CorpStatus, Facility

RULES = replace(GameConfig(), facility_rules=True)
OPEN_RULES = replace(RULES, asteroid_fraction=0.0, nebula_fraction=0.0)
"""Tests that build specific tiles run on an empty sky."""

CORELLIA = Hex(-5, 3)
ALDERAAN = Hex(-4, 1)
KUAT = Hex(-3, 2)
CORUSCANT = Hex(-6, 0)
BETWEEN = Hex(-4, 2)
"""Next to Corellia (its NE side), Alderaan (SE side) and Kuat (W side)."""
WEST_OF_BETWEEN = Hex(-5, 2)
"""Next to Corellia (its NW side) and Alderaan (SW side)."""


def new_game(config=OPEN_RULES, seed=1, players=3):
    return Game.new([f"Player {i + 1}" for i in range(players)], config, seed)


def float_corp(game, corp_id, par=60):
    p1, p2, p3 = game.players[:3]
    for player, extra in ((p1, par), (p2, 0), (p3, 0), (p2, 0)):
        game.apply_stock_action(player, BuyShare(corp_id, ShareSource.IPO, extra), set())
    corp = game.corp(corp_id)
    assert corp.floated
    return corp


def chart(game, corp, hex, *exits):
    game.apply_network_action(corp, Chart(hex, frozenset(exits), game.chart_cost(hex)))


def build(game, corp, planet, side=None):
    game.apply_fleet_action(corp, BuildFacility(planet, side, game.fleet_price()))


def log_texts(game, start=0):
    return [str(e) for e in game.log[start:]]


def reach_also(game, corp, *planets):
    """Pretend ``corp`` reaches ``planets`` as well, to place facilities where a test needs
    them without building the lanes."""
    real = game.reachable

    def reachable(c):
        found = real(c)
        return found | frozenset(planets) if c is corp else found

    game.reachable = reachable  # type: ignore[method-assign]


def fill_stages(game, stages):
    """Put enough cubes on the track to fill ``stages`` stages and apply their results."""
    game.death_star.cubes = stages * game.config.death_star_cubes_per_stage
    game.resolve_death_star()


def seize(game):
    """Fill the track through the next seizure stage and apply it (and any stage before)."""
    results = game.config.death_star_stage_results
    index = results.index(SEIZURE, game.death_star_stage())
    fill_stages(game, index + 1)


# --- configuration -----------------------------------------------------------------------------


def test_facility_rules_require_the_death_star_rules():
    with pytest.raises(ValueError, match="requires death_star_rules"):
        replace(CLASSIC_CONFIG, facility_rules=True).validate_rule_variants()


@pytest.mark.parametrize("overrides", [{"planet_base_exits": -1}, {"facilities_per_planet": 0}])
def test_bad_facility_numbers_are_rejected(overrides):
    with pytest.raises(ValueError):
        replace(RULES, **overrides).validate_rule_variants()


def test_facility_rules_are_off_by_default_and_planets_keep_every_exit():
    assert not GameConfig().facility_rules
    game = new_game(replace(OPEN_RULES, facility_rules=False))
    for planet in game.board.planets:
        assert not game.network.has_exit_limit(planet.hex)
        assert all(game.network.has_exit(planet.hex, d) for d in D)


def test_planets_start_with_one_unclaimed_exit_and_the_site_keeps_every_exit():
    game = new_game()
    site = game.death_star_site()
    for planet in game.board.planets:
        if planet.name == SITE_NAME:
            assert not game.network.has_exit_limit(planet.hex)
            assert all(game.network.has_exit(site, d) for d in D)
            continue
        assert game.network.planet_exits(planet.hex) == 1
        assert game.network.claimed_exits(planet.hex) == frozenset()
        assert not any(game.network.has_exit(planet.hex, d) for d in D)


def test_build_facility_reads_well():
    assert str(BuildFacility(ALDERAAN, D.SW, 60)) == (
        "build a facility at (-4,1) for 60 (exit toward (-5,2))"
    )
    assert (
        str(BuildFacility(ALDERAAN, None, 90))
        == "build a facility at (-4,1) for 90 (exit unclaimed)"
    )


# --- floating ----------------------------------------------------------------------------------


def test_a_corporation_floats_with_a_free_home_facility_outside_the_supply():
    game = new_game()
    cec = float_corp(game, "CEC")
    assert cec.fleets == 1
    assert game.facilities_of(cec) == [Facility(CORELLIA, "CEC", 0)]
    assert game.network.planet_exits(CORELLIA) == 2
    assert game.network.claimed_exits(CORELLIA) == frozenset()
    assert game.fleets_sold == 0 and game.fleet_price() == 60
    assert "[setup] CEC: gets a free facility at Corellia, its homeworld; owns 1" in log_texts(game)
    assert game.pair_cap(cec) == 1


def test_an_unfloated_homeworld_keeps_a_slot_for_its_corporation():
    game = new_game()
    cec = float_corp(game, "CEC")
    assert game.free_facility_slots(ALDERAAN) == 2
    assert game.free_facility_slots(KUAT) == 1, "one of Kuat's two slots waits for KDY"
    assert game.free_facility_slots(CORELLIA) == 1, "the home facility fills one"
    reach_also(game, cec, KUAT)
    build(game, cec, KUAT)
    assert game.free_facility_slots(KUAT) == 0
    assert KUAT not in game.facility_planets(cec)
    with pytest.raises(IllegalAction, match="no free facility slot"):
        build(game, cec, KUAT)
    kdy = float_corp(game, "KDY")
    assert [f.owner for f in game.facilities_on(KUAT)] == ["CEC", "KDY"]
    assert kdy.fleets == 1
    assert game.network.planet_exits(KUAT) == 3


# --- planet exits ------------------------------------------------------------------------------


def test_charting_toward_planets_claims_their_exits():
    game = new_game()
    cec = float_corp(game, "CEC")
    start = len(game.log)
    chart(game, cec, BETWEEN, D.SW, D.NW)
    assert game.network.claimed_exits(CORELLIA) == {D.NE}
    assert game.network.claimed_exits(ALDERAAN) == {D.SE}
    assert ALDERAAN in game.reachable(cec)
    assert log_texts(game, start) == [
        "[setup] CEC: chart (-4,2) exits SW/NW for 60; claims an exit of Corellia; claims an exit "
        "of Alderaan"
    ]


def test_a_lane_toward_a_planet_with_no_unclaimed_exit_dangles():
    game = new_game()
    cec = float_corp(game, "CEC")
    chart(game, cec, BETWEEN, D.SW, D.NW)
    start = len(game.log)
    # Corellia still has an unclaimed exit, so the tile connects there; Alderaan's one is gone.
    chart(game, cec, WEST_OF_BETWEEN, D.SE, D.NE)
    assert "its exit toward Alderaan dangles" in log_texts(game, start)[0]
    assert game.network.claimed_exits(CORELLIA) == {D.NE, D.NW}
    assert game.network.claimed_exits(ALDERAAN) == {D.SE}
    assert game.network.dangling_sides(ALDERAAN) == {D.SW}
    assert not game.network.connected(WEST_OF_BETWEEN, ALDERAAN)
    assert WEST_OF_BETWEEN in game.reachable(cec)


def test_a_tile_must_connect_through_another_exit_when_the_planet_is_full():
    game = new_game()
    cec = float_corp(game, "CEC")
    chart(game, cec, BETWEEN, D.SW, D.NW)
    north_of_alderaan = Hex(-4, 0)
    with pytest.raises(IllegalAction, match="would not connect"):
        chart(game, cec, north_of_alderaan, D.SE, D.NE)
    legal = game.legal_network_actions(cec)
    assert not any(isinstance(a, Chart) and a.hex == north_of_alderaan for a in legal)


def test_a_reached_planet_with_an_unclaimed_exit_connects_on_any_side():
    game = new_game()
    cec = float_corp(game, "CEC")
    legal = game.legal_network_actions(cec)
    toward_corellia = {a.hex for a in legal if isinstance(a, Chart)}
    # Every space neighbour of Corellia can be charted toward it: its exits have no direction.
    neighbours = {n for _, n in game.board.neighbors(CORELLIA) if not game.board.is_planet(n)}
    assert neighbours <= toward_corellia


def test_upgrading_toward_a_planet_claims_its_exit():
    game = new_game()
    cec = float_corp(game, "CEC")
    chart(game, cec, BETWEEN, D.SW, D.NW)
    start = len(game.log)
    game.apply_network_action(cec, Upgrade(BETWEEN, D.E, game.config.upgrade_cost))
    assert game.network.claimed_exits(KUAT) == {D.W}
    assert KUAT in game.reachable(cec)
    assert log_texts(game, start) == [
        "[setup] CEC: upgrade (-4,2) add E for 80; claims an exit of Kuat"
    ]


def test_an_upgrade_claims_only_through_its_new_exit():
    game = new_game()
    cec = float_corp(game, "CEC")
    chart(game, cec, BETWEEN, D.SW, D.NW)
    chart(game, cec, WEST_OF_BETWEEN, D.SE, D.NE)
    build(game, cec, ALDERAAN)  # its new exit is left unclaimed
    assert game.network.unclaimed_exits(ALDERAAN) == 1
    game.apply_network_action(cec, Upgrade(WEST_OF_BETWEEN, D.NW, game.config.upgrade_cost))
    assert game.network.claimed_exits(ALDERAAN) == {D.SE}, "the old dangling exit stays put"
    assert game.network.dangling_sides(ALDERAAN) == {D.SW}


def test_a_facility_can_give_its_new_exit_to_a_dangling_lane():
    game = new_game()
    cec = float_corp(game, "CEC")
    chart(game, cec, BETWEEN, D.SW, D.NW)
    chart(game, cec, WEST_OF_BETWEEN, D.SE, D.NE)
    options = [
        a
        for a in game.legal_fleet_actions(cec)
        if isinstance(a, BuildFacility) and a.planet == ALDERAAN
    ]
    assert options == [BuildFacility(ALDERAAN, None, 60), BuildFacility(ALDERAAN, D.SW, 60)]
    start = len(game.log)
    build(game, cec, ALDERAAN, D.SW)
    assert game.network.claimed_exits(ALDERAAN) == {D.SE, D.SW}
    assert game.network.connected(WEST_OF_BETWEEN, ALDERAAN)
    assert log_texts(game, start) == [
        "[setup] CEC: builds a facility at Alderaan for 60 (exit toward (-5,2)); owns 2"
    ]
    with pytest.raises(IllegalAction, match="No lane dangles"):
        build(game, cec, ALDERAAN, D.SW)


def test_a_new_unclaimed_exit_goes_to_the_next_tile_charted_toward_the_planet():
    game = new_game()
    cec = float_corp(game, "CEC")
    chart(game, cec, BETWEEN, D.SW, D.NW)
    build(game, cec, ALDERAAN)
    chart(game, cec, Hex(-4, 0), D.SE, D.NE)
    assert game.network.claimed_exits(ALDERAAN) == {D.SE, D.NW}


def test_a_network_passes_through_a_planet_only_through_two_claimed_exits():
    net = HyperspaceNetwork(load_board())
    net.limit_planet_exits((p.hex for p in net.board.planets), 1)
    net.chart("A", BETWEEN, frozenset({D.SW, D.NW}), net.reachable("A", CORELLIA))
    assert ALDERAAN in net.reachable("A", CORELLIA)
    # B comes from Coruscant toward Alderaan's west side, which has no exit for it.
    net.chart("B", Hex(-5, 0), frozenset({D.W, D.SE}), net.reachable("B", CORUSCANT))
    net.chart("B", Hex(-5, 1), frozenset({D.NW, D.E}), net.reachable("B", CORUSCANT))
    assert ALDERAAN not in net.reachable("B", CORUSCANT)
    # Alderaan is a dead end for A, and extending service claims nothing.
    with pytest.raises(IllegalAction, match="not connected"):
        net.extend_service("A", Hex(-5, 1), net.reachable("A", CORELLIA))
    net.add_planet_exit(ALDERAAN)
    net.claim_exit(ALDERAAN, D.W)
    net.extend_service("A", Hex(-5, 1), net.reachable("A", CORELLIA))
    net.extend_service("A", Hex(-5, 0), net.reachable("A", CORELLIA))
    assert CORUSCANT in net.reachable("A", CORELLIA)
    assert ALDERAAN in net.reachable("B", CORUSCANT)


def test_what_if_copies_carry_planet_exits_independently():
    game = new_game()
    cec = float_corp(game, "CEC")
    copy = game.network.copy()
    copy.chart("CEC", BETWEEN, frozenset({D.SW, D.NW}), copy.reachable("CEC", CORELLIA))
    copy.add_planet_exit(ALDERAAN)
    assert game.network.claimed_exits(CORELLIA) == frozenset()
    assert game.network.planet_exits(ALDERAAN) == 1
    assert ALDERAAN not in game.reachable(cec)


def test_the_site_moving_changes_no_planet_exits():
    game = new_game()
    cec = float_corp(game, "CEC")
    chart(game, cec, BETWEEN, D.SW, D.NW)
    build(game, cec, ALDERAAN)
    limited = [p.hex for p in game.board.planets if game.network.has_exit_limit(p.hex)]

    def exits():
        return {h: (game.network.planet_exits(h), game.network.claimed_exits(h)) for h in limited}

    before = exits()
    fill_stages(game, 2)  # a seizure, then the site moves
    assert game.death_star_site() == game.death_star.sites[1]
    assert exits() == before
    assert not game.network.has_exit_limit(game.death_star_site())


# --- where a facility may go ------------------------------------------------------------------


def test_facility_planets_are_reached_pointed_at_or_already_held():
    game = new_game(replace(OPEN_RULES, planet_base_exits=0))
    cec = float_corp(game, "CEC")
    chart(game, cec, BETWEEN, D.SW, D.NW)
    # Alderaan has no exit at all, so the lane dangles there: CEC does not reach it, but points
    # a served, reachable tile at it.
    assert ALDERAAN not in game.reachable(cec)
    assert game.facility_planets(cec) == sorted([CORELLIA, ALDERAAN])
    build(game, cec, ALDERAAN, D.SE)
    assert ALDERAAN in game.reachable(cec)
    # Cut off from Alderaan, CEC may still build there because it holds a facility.
    game.reachable = lambda corp: frozenset({CORELLIA})  # type: ignore[method-assign]
    assert game.facility_planets(cec) == sorted([CORELLIA, ALDERAAN])
    with pytest.raises(IllegalAction, match="neither reaches Kuat"):
        game.apply_fleet_action(cec, BuildFacility(KUAT, None, game.fleet_price()))


def test_a_planet_holds_at_most_two_facilities():
    game = new_game()
    cec = float_corp(game, "CEC")
    chart(game, cec, BETWEEN, D.SW, D.NW)
    build(game, cec, ALDERAAN)
    build(game, cec, ALDERAAN)
    assert game.network.planet_exits(ALDERAAN) == 3
    assert ALDERAAN not in game.facility_planets(cec)
    with pytest.raises(IllegalAction, match="no free facility slot"):
        build(game, cec, ALDERAAN)


def test_no_facility_on_the_construction_site():
    game = new_game()
    cec = float_corp(game, "CEC")
    site = game.death_star_site()
    reach_also(game, cec, site)
    assert site not in game.facility_planets(cec)
    with pytest.raises(IllegalAction, match="not a planet that can hold a facility"):
        game.apply_fleet_action(cec, BuildFacility(site, None, game.fleet_price()))


# --- price, limit and capacity ----------------------------------------------------------------


def test_facilities_are_priced_by_the_fleet_tiers():
    game = new_game()
    cec = float_corp(game, "CEC")
    reach_also(game, cec, ALDERAAN, KUAT)
    game.fleets_sold = 5
    start = len(game.log)
    build(game, cec, ALDERAAN)
    assert cec.treasury == 480 - 60
    assert game.fleets_sold == 6 and game.fleet_price() == 90
    assert "[setup] Empire: facility price rises to 90" in log_texts(game, start)
    assert {a.cost for a in game.legal_fleet_actions(cec) if isinstance(a, BuildFacility)} == {90}
    with pytest.raises(IllegalAction, match="costs 90 now"):
        game.apply_fleet_action(cec, BuildFacility(KUAT, None, 60))


def test_the_fleet_limit_caps_facilities_and_fleets_cannot_be_bought():
    game = new_game()
    cec = float_corp(game, "CEC")
    reach_also(game, cec, ALDERAAN, KUAT)
    with pytest.raises(IllegalAction):
        game.apply_fleet_action(cec, BuyFleet(game.fleet_price()))
    build(game, cec, ALDERAAN)
    build(game, cec, ALDERAAN)
    build(game, cec, KUAT)
    assert cec.fleets == game.config.fleet_limit == 4
    assert game.legal_fleet_actions(cec) == [FinishFleets()]
    with pytest.raises(IllegalAction, match="the limit"):
        build(game, cec, CORELLIA)


def test_pair_capacity_is_the_facilities_owned():
    game = new_game()
    cec = float_corp(game, "CEC")
    reach_also(game, cec, ALDERAAN)
    planets = [Planet(f"p{i}", Hex(i, 0), "Mid Rim", frozenset(t)) for i, t in enumerate("AMRSIM")]
    game.reachable_planets = lambda corp: planets  # type: ignore[method-assign]
    totals = []
    for _ in range(3):
        assert game.pair_cap(cec) == cec.fleets == len(game.facilities_of(cec))
        totals.append(game.revenue(cec).total)
        build(game, cec, ALDERAAN if cec.fleets < 3 else CORELLIA)
    assert totals == [30, 60, 90]


def test_the_facility_step_must_end_owning_a_facility():
    game = new_game()
    cec = float_corp(game, "CEC")
    seize(game)
    assert cec.fleets == 0
    legal = game.legal_fleet_actions(cec)
    assert legal and all(isinstance(a, BuildFacility) for a in legal)
    with pytest.raises(IllegalAction, match="must own a facility"):
        game.apply_fleet_action(cec, FinishFleets())
    start = len(game.log)
    build(game, cec, CORELLIA)
    game.apply_fleet_action(cec, FinishFleets())
    assert log_texts(game, start)[-1] == "[setup] CEC: finishes building facilities with 1"


def test_session_runs_the_facility_step_between_network_and_dividend():
    game = new_game()
    float_corp(game, "CEC")
    session = GameSession(game)
    for _ in game.players:
        session.apply(PassStock())
    session.apply(NoNetworkAction())
    assert session.phase is Phase.FLEET
    assert session.legal_actions() == [BuildFacility(CORELLIA, None, 60), FinishFleets()]
    session.apply(BuildFacility(CORELLIA, None, 60))
    session.apply(FinishFleets())
    assert session.phase is Phase.DIVIDEND


# --- seizure ----------------------------------------------------------------------------------


def test_seizure_takes_the_facility_nearest_the_site_and_makes_it_imperial():
    game = new_game()
    cec = float_corp(game, "CEC")
    site = game.death_star_site()
    others = [p.hex for p in game.board.planets if game.network.has_exit_limit(p.hex)]
    near = min((h for h in others if h != CORELLIA), key=site.distance)
    far = max(others, key=site.distance)
    assert site.distance(near) < site.distance(CORELLIA) < site.distance(far)
    reach_also(game, cec, near, far)
    build(game, cec, far)
    build(game, cec, near)
    build(game, cec, far)
    exits = game.network.planet_exits(near)
    start = len(game.log)
    seize(game)
    name = game.board.planet_at(near).name
    assert log_texts(game, start)[-1] == (
        f"[setup] Empire: takes over CEC's facility at {name}; it owns 3"
    )
    assert [f.owner for f in game.facilities_on(near)] == [EMPIRE]
    assert game.network.planet_exits(near) == exits, "the exit stays"
    assert game.free_facility_slots(near) == 1, "the slot stays filled"
    assert cec.fleets == len(game.facilities_of(cec)) == 3
    assert game.facility_seizure_ties == 0
    assert game.fleets_sold == 3, "a seized facility does not return to the supply"


def test_seizure_tie_takes_the_most_recently_built_and_is_counted():
    game = new_game()
    cec = float_corp(game, "CEC")
    site = game.death_star_site()
    limited = [p.hex for p in game.board.planets if game.network.has_exit_limit(p.hex)]
    distance = site.distance(CORELLIA)
    twin = next(h for h in limited if h != CORELLIA and site.distance(h) == distance)
    reach_also(game, cec, twin)
    build(game, cec, twin)
    seize(game)
    assert [f.owner for f in game.facilities_on(twin)] == [EMPIRE]
    assert [f.owner for f in game.facilities_on(CORELLIA)] == ["CEC"]
    assert game.facility_seizure_ties == 1


def test_two_nearest_facilities_on_one_planet_are_no_tie():
    game = new_game()
    cec = float_corp(game, "CEC")
    build(game, cec, CORELLIA)
    seize(game)
    assert [f.owner for f in game.facilities_on(CORELLIA)] == ["CEC", EMPIRE]
    assert game.facility_seizure_ties == 0


def test_seizure_spares_corporations_without_facilities():
    game = new_game()
    cec = float_corp(game, "CEC")
    seize(game)
    start = len(game.log)
    seize(game)
    texts = log_texts(game, start)
    assert any("finds no facilities to take over" in t for t in texts)
    assert cec.fleets == 0


# --- bankruptcy -------------------------------------------------------------------------------


def test_a_corporation_without_a_facility_or_the_money_for_one_is_bankrupt():
    game = new_game()
    cec = float_corp(game, "CEC")
    seize(game)
    cec.treasury = 59
    assert game.must_close(cec)
    game.close_bankrupt(cec)
    assert cec.status is CorpStatus.CLOSED
    assert "no facility, and its treasury of 59 cannot build one at 60" in log_texts(game)[-1]


def test_a_corporation_with_money_but_nowhere_to_build_is_bankrupt():
    game = new_game(replace(OPEN_RULES, facilities_per_planet=1))
    cec = float_corp(game, "CEC")
    seize(game)  # Corellia's only slot is Imperial now
    assert cec.treasury >= game.fleet_price()
    assert game.legal_fleet_actions(cec) == []
    assert game.must_close(cec)
    game.close_bankrupt(cec)
    assert "no facility, and no planet it may build one on" in log_texts(game)[-1]


def test_a_corporation_that_can_build_is_not_bankrupt():
    game = new_game()
    cec = float_corp(game, "CEC")
    assert not game.must_close(cec), "it owns its home facility"
    seize(game)
    assert not game.must_close(cec), "it can rebuild on its homeworld"
    with pytest.raises(IllegalAction):
        game.close_bankrupt(cec)


def test_session_closes_a_corporation_that_cannot_build_at_its_facility_step():
    game = new_game(replace(OPEN_RULES, facilities_per_planet=1))
    cec = float_corp(game, "CEC")
    kdy = float_corp(game, "KDY")
    seize(game)
    session = GameSession(game)
    for _ in game.players:
        session.apply(PassStock())
    assert session.operating_queue[0] == "CEC"
    session.apply(NoNetworkAction())
    assert cec.status is CorpStatus.CLOSED
    assert session.phase is Phase.NETWORK and session.current_corporation is kdy


# --- whole games ------------------------------------------------------------------------------


def _check_invariants(game):
    net = game.network
    for corp in game.corporations.values():
        assert corp.fleets == len(game.facilities_of(corp))
        assert 0 <= corp.fleets <= game.config.fleet_limit
    for planet in game.board.planets:
        hex = planet.hex
        if not net.has_exit_limit(hex):
            assert planet.name == SITE_NAME
            continue
        on = game.facilities_on(hex)
        assert len(on) <= game.config.facilities_per_planet
        assert net.planet_exits(hex) == game.config.planet_base_exits + len(on)
        claimed = net.claimed_exits(hex)
        assert len(claimed) <= net.planet_exits(hex)
        for side in claimed:
            tile = net.tile_at(hex.neighbor(side))
            assert tile is not None and side.opposite in tile.exits


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_bot_games_under_facility_rules_run_to_the_end(seed):
    game, summary = play_one(seed, 3, "mix:baron,early-builder,targeted", RULES)
    assert game.is_over()
    assert game.round_number <= RULES.death_star_backstop_rounds
    player_cash = sum(p.cash for p in game.players)
    corp_cash = sum(c.treasury for c in game.corporations.values())
    assert player_cash + corp_cash + game.bank == 3 * RULES.starting_cash(3)
    _check_invariants(game)
    assert summary.death_star is not None
    metrics = summary.death_star.corps.values()
    assert sum(m.fleets_bought for m in metrics) == game.fleets_sold
    imperial = sum(1 for f in game.facilities if f.owner == EMPIRE)
    assert sum(m.fleets_seized for m in metrics) == imperial


@pytest.mark.parametrize("players,seed", [(3, 6), (4, 7)])
def test_random_bots_under_facility_rules_keep_every_invariant(players, seed):
    game, _ = play_one(seed, players, "random", RULES)
    assert game.is_over()
    _check_invariants(game)


def test_bot_games_under_facility_rules_are_deterministic():
    first, _ = play_one(8, 3, "mix:baron,early-builder,targeted", RULES)
    second, _ = play_one(8, 3, "mix:baron,early-builder,targeted", RULES)
    assert log_texts(first) == log_texts(second)
