"""How the greedy bots plan routes and build facilities under the experimental facility rules
(``facility_rules``): planet exits in route costs (``bby18.bots.routing``) and the facility
step (``GreedyBot._choose_facility``)."""

import random
from dataclasses import replace

from bby18.actions import BuildFacility, BuyShare, Chart, FinishFleets, ShareSource, Upgrade
from bby18.bots import GreedyBot
from bby18.bots.forecast import TrackForecast
from bby18.bots.greedy import NO_ROUTE_COST, _FacilityOption
from bby18.bots.routing import PlanetDoors, route_costs
from bby18.bots.stable import STABLE
from bby18.config import GameConfig, SEIZURE
from bby18.game import Game
from bby18.hexgrid import Direction as D
from bby18.hexgrid import Hex

RULES = replace(GameConfig(), facility_rules=True)
OPEN_RULES = replace(RULES, asteroid_fraction=0.0, nebula_fraction=0.0)
"""Tests that build specific tiles run on an empty sky."""

CORELLIA = Hex(-5, 3)
ALDERAAN = Hex(-4, 1)
KUAT = Hex(-3, 2)
BETWEEN = Hex(-4, 2)
"""Next to Corellia (its NE side), Alderaan (SE side) and Kuat (W side)."""
WEST_OF_BETWEEN = Hex(-5, 2)
"""Next to Corellia (its NW side) and Alderaan (SW side)."""
NORTH_OF_ALDERAAN = Hex(-4, 0)
"""Alderaan's NW neighbour."""
EAST_OF_ALDERAAN = Hex(-3, 1)
"""Next to Alderaan (its E side) and Kuat (NW side)."""
SOUTHWEST_OF_CORELLIA = Hex(-6, 4)


def new_game(config=OPEN_RULES, seed=1):
    return Game.new([f"Player {i + 1}" for i in range(3)], config, seed)


def float_corp(game, corp_id, par=60):
    p1, p2, p3 = game.players[:3]
    for player, extra in ((p1, par), (p2, 0), (p3, 0), (p2, 0)):
        game.apply_stock_action(player, BuyShare(corp_id, ShareSource.IPO, extra), set())
    corp = game.corp(corp_id)
    assert corp.floated
    return corp


def chart(game, corp, hex, *exits):
    game.apply_network_action(corp, Chart(hex, frozenset(exits), game.chart_cost(hex)))


def bot(name="baron"):
    return GreedyBot(random.Random(0), STABLE[name])


def doors_of(game, corp, **changes):
    doors = PlanetDoors.of(game, corp)
    assert doors is not None
    return replace(doors, **changes)


def costs_to(game, corp, target, doors):
    return route_costs(game, game.network, corp.id, [target], frozenset(), doors)


def builds(game, corp):
    return [a for a in game.legal_fleet_actions(corp) if isinstance(a, BuildFacility)]


# --- route costs -------------------------------------------------------------------------------


def test_a_route_through_a_full_planet_pays_for_the_facility_that_opens_it():
    game = new_game()
    cec = float_corp(game, "CEC")
    chart(game, cec, BETWEEN, D.SW, D.NW)  # takes Alderaan's only exit
    price = game.fleet_price()
    door_aware = costs_to(game, cec, NORTH_OF_ALDERAAN, PlanetDoors.of(game, cec))
    assert door_aware[BETWEEN] == price, "through Alderaan once a facility opens its NW side"
    assert costs_to(game, cec, NORTH_OF_ALDERAAN, None)[BETWEEN] == 0, "an open hub is free"
    full = doors_of(game, cec, slots={**doors_of(game, cec).slots, ALDERAAN: 0})
    around = costs_to(game, cec, NORTH_OF_ALDERAAN, full)[BETWEEN]
    assert around == 2 * OPEN_RULES.chart_cost, "with no slot left the route goes round"


def test_a_one_exit_planet_is_a_dead_end_unless_a_facility_is_bought():
    game = new_game()
    cec = float_corp(game, "CEC")
    doors = PlanetDoors.of(game, cec)
    assert doors is not None
    assert doors.cost(ALDERAAN, {D.SE}) == 0, "ending there takes its one exit"
    assert doors.cost(ALDERAAN, {D.SE, D.NW}) == game.fleet_price(), "passing needs two"
    at_limit = doors_of(game, cec, can_build=False)
    assert at_limit.cost(ALDERAAN, {D.SE, D.NW}) is None
    # A route from beside Alderaan to the hex beyond it is charted round, never passed free.
    to_go = costs_to(game, cec, NORTH_OF_ALDERAAN, at_limit)
    assert to_go[BETWEEN] >= OPEN_RULES.chart_cost


def test_routes_are_never_cheaper_with_planet_exits_than_without():
    game = new_game(RULES, seed=3)
    cec = float_corp(game, "CEC")
    chart_options = [a for a in game.legal_network_actions(cec) if isinstance(a, Chart)]
    game.apply_network_action(cec, chart_options[0])
    targets = [p.hex for p in game.board.planets if p.hex not in game.reachable(cec)]
    open_hubs = route_costs(game, game.network, "CEC", targets, frozenset(), None)
    doors = route_costs(game, game.network, "CEC", targets, frozenset(), PlanetDoors.of(game, cec))
    for hex, cost in doors.items():
        assert cost >= open_hubs[hex], hex


def test_leaving_the_network_pays_for_the_tile_or_planet_side_it_leaves_by():
    game = new_game()
    cec = float_corp(game, "CEC")
    chart(game, cec, BETWEEN, D.SW, D.NW)
    doors = PlanetDoors.of(game, cec)
    assert doors is not None
    assert doors.leaving_cost(BETWEEN, D.NW) == 0, "through one of its exits"
    assert doors.leaving_cost(BETWEEN, D.E) == OPEN_RULES.upgrade_cost
    assert doors.leaving_cost(ALDERAAN, D.NW) == game.fleet_price(), "Alderaan is full"
    assert doors.leaving_cost(CORELLIA, D.SE) == 0, "the home facility's spare exit"
    game.apply_network_action(cec, Upgrade(BETWEEN, D.E, OPEN_RULES.upgrade_cost))
    assert PlanetDoors.of(game, cec).leaving_cost(BETWEEN, D.SE) is None, "three exits already"


def test_a_lane_toward_a_full_planet_is_priced_as_the_first_step_of_a_facility_there():
    game = new_game()
    cec = float_corp(game, "CEC")
    kdy = float_corp(game, "KDY")
    chart(game, kdy, EAST_OF_ALDERAAN, D.SE, D.W)  # KDY takes Alderaan's only exit
    greedy = bot()
    reach = game.reachable(cec)
    to_go = greedy._weighted_route_costs(game, cec, {ALDERAAN: 1.0}, frozenset())
    dangling = Chart(BETWEEN, frozenset({D.SW, D.NW}), OPEN_RULES.chart_cost)
    assert dangling in game.legal_network_actions(cec)
    price = game.fleet_price()
    assert greedy._remaining_route_cost(game, dangling, reach, to_go) == price
    slots = game.free_facility_slots

    def no_slot_on_alderaan(planet):
        return 0 if planet == ALDERAAN else slots(planet)

    game.free_facility_slots = no_slot_on_alderaan  # type: ignore[method-assign]
    to_go = greedy._weighted_route_costs(game, cec, {ALDERAAN: 1.0}, frozenset())
    assert greedy._remaining_route_cost(game, dangling, reach, to_go) == NO_ROUTE_COST


# --- the facility step ------------------------------------------------------------------------


def test_the_facility_step_gives_its_exit_to_its_own_lane_to_connect_a_planet():
    game = new_game(replace(OPEN_RULES, planet_base_exits=0))
    cec = float_corp(game, "CEC")
    chart(game, cec, BETWEEN, D.SW, D.NW)  # dangles at Alderaan, which has no exit at all
    assert ALDERAAN not in game.reachable(cec)
    legal = game.legal_fleet_actions(cec)
    choice = bot().choose_fleet_action(game, cec, legal)
    assert choice == BuildFacility(ALDERAAN, D.SE, game.fleet_price())


def test_a_facility_that_opens_the_way_to_a_target_is_built_though_its_pair_earns_nothing():
    game = new_game()
    cec = float_corp(game, "CEC")
    chart(game, cec, BETWEEN, D.SW, D.NW)
    chart(game, cec, WEST_OF_BETWEEN, D.SE, D.NE)
    # Corellia's two exits and Alderaan's one are claimed: every way out needs a facility or an
    # upgrade, and two planets run one pair whatever CEC owns.
    greedy = bot()
    greedy._death_star_targets = lambda game, forecast, reach: {  # type: ignore[method-assign]
        SOUTHWEST_OF_CORELLIA: 1.0
    }
    options = greedy._facility_options(game, TrackForecast.of(game), cec, builds(game, cec))
    assert {o.marginal for o in options} == {0}
    corellia = next(o for o in options if o.action.planet == CORELLIA)
    assert corellia.route_saving == game.fleet_price()
    choice = greedy.choose_fleet_action(game, cec, game.legal_fleet_actions(cec))
    assert choice == BuildFacility(CORELLIA, None, game.fleet_price())
    # In the last turn there is no time left to build along the route.
    game.round_number = game.round_limit() - 1
    game.round_label = f"OR{game.round_number + 1}.2"
    assert TrackForecast.of(game).turns_left == 1
    assert greedy.choose_fleet_action(game, cec, game.legal_fleet_actions(cec)) == FinishFleets()


def test_the_new_exit_goes_to_the_builders_lane_then_unclaimed_then_a_rivals():
    game = new_game()
    cec = float_corp(game, "CEC")
    kdy = float_corp(game, "KDY")
    chart(game, cec, BETWEEN, D.SW, D.NW)
    chart(game, cec, WEST_OF_BETWEEN, D.SE, D.NE)  # CEC's lane dangles on Alderaan's SW
    chart(game, kdy, EAST_OF_ALDERAAN, D.SE, D.W)  # KDY's on its E
    at_alderaan = [a for a in builds(game, cec) if a.planet == ALDERAAN]
    gifts = {a.exit_side: GreedyBot._exit_gift(game, cec, a) for a in at_alderaan}
    assert gifts == {D.SW: 0, None: 1, D.E: 2}
    admiral = bot("admiral")

    def equal_but_for_the_gift(game, forecast, corp, builds):
        return [_FacilityOption(a, 0, 0, 0.0, NO_ROUTE_COST, gifts[a.exit_side], 3) for a in builds]

    admiral._facility_options = equal_but_for_the_gift  # type: ignore[method-assign]
    forecast = TrackForecast.of(game)
    ranked = sorted(at_alderaan, key=lambda a: gifts[a.exit_side])
    for best, rest in ((ranked[0], ranked), (ranked[1], ranked[1:])):
        assert admiral._facility_choice(game, forecast, cec, list(reversed(rest))) == best


def test_a_fleet_target_policy_builds_facilities_up_to_its_target_and_stops():
    game = new_game()
    cec = float_corp(game, "CEC")
    chart(game, cec, BETWEEN, D.SW, D.NW)
    admiral = bot("admiral")
    assert STABLE["admiral"].fleet_target == 4
    while (choice := admiral.choose_fleet_action(game, cec, game.legal_fleet_actions(cec))) != (
        FinishFleets()
    ):
        game.apply_fleet_action(cec, choice)
    assert cec.fleets == len(game.facilities_of(cec)) == 4


def test_a_corporation_left_without_a_facility_always_builds_one():
    game = new_game()
    cec = float_corp(game, "CEC")
    results = game.config.death_star_stage_results
    game.death_star.cubes = (results.index(SEIZURE) + 1) * game.config.death_star_cubes_per_stage
    game.resolve_death_star()
    assert cec.fleets == 0
    choice = bot().choose_fleet_action(game, cec, game.legal_fleet_actions(cec))
    assert isinstance(choice, BuildFacility)


def test_a_facility_it_wants_but_cannot_pay_for_counts_as_needing_cash():
    game = new_game(replace(OPEN_RULES, planet_base_exits=0))
    cec = float_corp(game, "CEC")
    chart(game, cec, BETWEEN, D.SW, D.NW)
    targeted = bot("targeted")
    forecast = TrackForecast.of(game)
    cec.treasury = game.fleet_price() - 1
    assert targeted._wants_unaffordable_fleet(game, forecast, cec)
    cec.treasury = game.fleet_price()
    assert not targeted._wants_unaffordable_fleet(game, forecast, cec), "it can pay"
