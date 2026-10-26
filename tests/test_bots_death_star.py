"""How the greedy bots play the experimental Death Star rules (``death_star_rules``)."""

import random
from dataclasses import replace

import pytest

from bby18.actions import (
    BuyFleet,
    BuyShare,
    FinishFleets,
    NoNetworkAction,
    SellShares,
    ShareSource,
)
from bby18.board import Planet
from bby18.bots import GreedyBot, GreedyPolicy
from bby18.bots.forecast import (
    NOTHING_AHEAD,
    RESERVE_HORIZON_TURNS,
    TrackForecast,
    cautious_fleet_price,
    is_fragile,
    turns_to_round_limit,
)
from bby18.bots.stable import STABLE
from bby18.config import CLASSIC_CONFIG
from bby18.death_star import SITE_NAME
from bby18.game import Game
from bby18.hexgrid import Hex
from bby18.playtest import play_one
from bby18.runner import run_game

RULES = replace(CLASSIC_CONFIG, death_star_rules=True)
"""The Death Star rules with the numbers they were built and tested with (6 cubes per stage,
sites anywhere that qualifies). ``CLASSIC_CONFIG`` adopted tighter numbers on 2026-10-26; these
tests pin the mechanics, not the adopted numbers."""
OPEN_RULES = replace(RULES, asteroid_fraction=0.0, nebula_fraction=0.0)
NEW_ARCHETYPES = ("admiral", "contractor", "staller", "saver", "raider")
DEATH_STAR_KNOB_DEFAULTS = {
    "fleet_payback_turns": GreedyPolicy.fleet_payback_turns,
    "fleet_target": GreedyPolicy.fleet_target,
    "contract_weight": GreedyPolicy.contract_weight,
    "treasury_reserve_fleets": GreedyPolicy.treasury_reserve_fleets,
    "sell_own_before_seizure": GreedyPolicy.sell_own_before_seizure,
}


def new_game(config=RULES, seed=1):
    return Game.new([f"Player {i + 1}" for i in range(3)], config, seed)


def float_corp(game, corp_id, par=60):
    p1, p2, p3 = game.players[:3]
    for player, extra in ((p1, par), (p2, 0), (p3, 0), (p2, 0)):
        game.apply_stock_action(player, BuyShare(corp_id, ShareSource.IPO, extra), set())
    corp = game.corp(corp_id)
    assert corp.floated
    return corp


def planets(tags: str, start: int = 0) -> list[Planet]:
    """One Mid Rim planet per tag letter, on distinct hexes."""
    return [
        Planet(f"p{start + i}", Hex(start + i, 20), "Mid Rim", frozenset({t}))
        for i, t in enumerate(tags)
    ]


def bot(**knobs) -> GreedyBot:
    return GreedyBot(random.Random(0), GreedyPolicy(routing="path", **knobs))


def seizure_next(game, round_label="OR2.2"):
    """Put the game in the last operating round of round 2 with the first seizure one cube
    away: the Empire's cube at the end of the round fills it."""
    game.round_number = 1
    game.round_label = round_label
    game.death_star.cubes = 5


def _log(game):
    return [str(e) for e in game.log]


# --- forecasts -------------------------------------------------------------------------------


def test_turns_to_the_backstop_count_the_current_operating_round():
    game = new_game()
    game.round_number = 2
    game.round_label = "OR3.2"
    assert turns_to_round_limit(game) == (RULES.death_star_backstop_rounds - 2) * 2 - 1
    game.round_label = "SR3"
    assert turns_to_round_limit(game) == (RULES.death_star_backstop_rounds - 2) * 2


def test_expected_turns_shrink_when_the_station_is_about_to_launch():
    game = new_game()
    float_corp(game, "CEC")
    game.round_label = "OR1.1"
    assert TrackForecast.of(game).turns_left == turns_to_round_limit(game)
    game.death_star.cubes = 23
    # The Empire's cube at the end of the round launches it; the game ends with that round.
    assert TrackForecast.of(game).turns_left == 2


def test_a_seizure_one_cube_away_comes_before_the_next_fleet_step_in_the_last_round():
    game = new_game()
    float_corp(game, "CEC")
    seizure_next(game)
    forecast = TrackForecast.of(game)
    assert forecast.seizure_deadline == 1
    assert forecast.seizure_before_next_fleet_step


def test_no_seizure_ahead_once_both_have_applied():
    game = new_game()
    float_corp(game, "CEC")
    game.death_star.cubes = 18
    game.death_star.stages_resolved = 3
    assert TrackForecast.of(game).seizure_deadline == NOTHING_AHEAD


def test_fleet_reserve_is_a_replacement_less_what_can_still_be_withheld():
    forecast = TrackForecast(
        turns_left=10,
        site_turns_left=10,
        rounds_to_site_move=10,
        seizure_deadline=3,
        seizure_within_round=True,
        cautious_price=90,
    )
    assert forecast.fleet_reserve(fleets=1, revenue=30) == 30
    assert forecast.fleet_reserve(fleets=1, revenue=50) == 0
    assert forecast.fleet_reserve(fleets=2, revenue=0) == 0
    assert replace(forecast, seizure_deadline=1).fleet_reserve(fleets=1, revenue=50) == 90
    assert replace(forecast, seizure_deadline=NOTHING_AHEAD).fleet_reserve(1, 0) == 0
    assert replace(forecast, seizure_deadline=RESERVE_HORIZON_TURNS + 1).fleet_reserve(1, 0) == 0


def test_cautious_price_is_the_next_tier_when_the_current_one_is_nearly_sold():
    game = new_game()
    game.fleets_sold = 3
    assert cautious_fleet_price(game) == 60
    game.fleets_sold = 4
    assert cautious_fleet_price(game) == 90
    game.fleets_sold = 30
    assert cautious_fleet_price(game) == 160


def test_a_corporation_without_a_replacement_before_a_seizure_is_fragile():
    game = new_game()
    cec = float_corp(game, "CEC")
    cec.fleets, cec.treasury = 1, 0
    seizure_next(game, round_label="SR3")
    forecast = TrackForecast.of(game)
    assert is_fragile(game, "CEC", forecast)
    cec.treasury = 90
    assert not is_fragile(game, "CEC", forecast)
    cec.treasury, cec.fleets = 0, 2
    assert not is_fragile(game, "CEC", forecast)
    cec.fleets = 0
    game.death_star.cubes = 0
    assert is_fragile(game, "CEC", TrackForecast.of(game)), "it cannot buy its mandatory fleet"


# --- survival --------------------------------------------------------------------------------


def test_bot_keeps_a_replacement_fleets_price_from_builds_before_a_seizure():
    game = new_game(OPEN_RULES)
    cec = float_corp(game, "CEC")
    cec.fleets, cec.treasury = 1, 110
    legal = game.legal_network_actions(cec)
    assert bot().choose_network_action(game, cec, legal) != NoNetworkAction()
    seizure_next(game)
    assert bot().choose_network_action(game, cec, legal) == NoNetworkAction()


def test_bot_with_no_fleet_never_builds_into_the_mandatory_fleets_price():
    game = new_game(OPEN_RULES)
    cec = float_corp(game, "CEC")
    cec.treasury = 100
    legal = game.legal_network_actions(cec)
    assert bot().choose_network_action(game, cec, legal) == NoNetworkAction()
    cec.treasury = 130
    choice = bot().choose_network_action(game, cec, game.legal_network_actions(cec))
    assert not isinstance(choice, NoNetworkAction) and choice.cost <= 70


def test_even_a_baron_withholds_when_paying_would_leave_no_replacement_fleet():
    game = new_game()
    cec = float_corp(game, "CEC")
    cec.fleets, cec.treasury = 1, 20
    baron = GreedyBot(random.Random(0), STABLE["baron"])
    assert baron.choose_pay_dividends(game, cec, 30)
    seizure_next(game)
    assert not baron.choose_pay_dividends(game, cec, 30)
    cec.treasury = 90
    assert baron.choose_pay_dividends(game, cec, 30)


def test_one_fleet_corporation_buys_a_second_that_earns_rather_than_hoarding_before_a_seizure():
    game = new_game()
    cec = float_corp(game, "CEC")
    cec.fleets = 1
    reach = planets("AMRSB")  # A-M typed 30, R-S typed 30, B left over
    game.reachable_planets = lambda corp: reach  # type: ignore[method-assign]
    slow = bot(fleet_payback_turns=1)  # 30 a turn for one turn never pays back 60
    assert slow.choose_fleet_action(game, cec, [BuyFleet(60), FinishFleets()]) == FinishFleets()
    seizure_next(game)
    assert slow.choose_fleet_action(game, cec, [BuyFleet(60), FinishFleets()]) == BuyFleet(60)


def test_competent_bots_do_not_go_bankrupt_on_these_seeds():
    for kind in ("builder", "baron", "saver"):
        for seed in (1, 2, 3):
            game, _ = play_one(seed, 3, kind, RULES)
            assert game.is_over()
            assert game.closed_corporations() == [], (kind, seed)


# --- fleet value -----------------------------------------------------------------------------


def test_fleets_are_bought_when_the_pair_they_add_pays_them_back():
    game = new_game()
    cec = float_corp(game, "CEC")
    cec.fleets = 1
    reach = planets("AMRS")  # two typed pairs of 30
    game.reachable_planets = lambda corp: reach  # type: ignore[method-assign]
    legal = [BuyFleet(60), FinishFleets()]
    assert bot().choose_fleet_action(game, cec, legal) == BuyFleet(60)  # 30 x 4 >= 60
    assert bot(fleet_payback_turns=1.5).choose_fleet_action(game, cec, legal) == FinishFleets()
    cec.fleets = 2  # no third pair to run
    assert bot().choose_fleet_action(game, cec, legal) == FinishFleets()


def test_fleet_value_counts_only_the_turns_the_game_has_left():
    game = new_game()
    cec = float_corp(game, "CEC")
    cec.fleets = 1
    reach = planets("AMRS")
    game.reachable_planets = lambda corp: reach  # type: ignore[method-assign]
    game.round_number = RULES.death_star_backstop_rounds - 1
    game.round_label = f"OR{RULES.death_star_backstop_rounds}.2"
    assert bot().choose_fleet_action(game, cec, [BuyFleet(60), FinishFleets()]) == FinishFleets()


def test_the_mandatory_first_fleet_is_always_bought():
    game = new_game()
    cec = float_corp(game, "CEC")
    game.reachable_planets = lambda corp: []  # type: ignore[method-assign]
    assert bot().choose_fleet_action(game, cec, [BuyFleet(60)]) == BuyFleet(60)


def test_fleet_target_buys_to_the_target_regardless_of_value_and_stops():
    game = new_game()
    cec = float_corp(game, "CEC")
    cec.fleets = 1
    reach = planets("AMRS")
    game.reachable_planets = lambda corp: reach  # type: ignore[method-assign]
    legal = [BuyFleet(60), FinishFleets()]
    cec.fleets = 3  # no fourth pair to run
    assert bot(fleet_target=4).choose_fleet_action(game, cec, legal) == BuyFleet(60)
    cec.fleets = 1  # a second pair worth 30 a turn
    assert bot(fleet_target=1).choose_fleet_action(game, cec, legal) == FinishFleets()


# --- builds under the pair cap ---------------------------------------------------------------


def test_a_build_is_valued_under_the_pair_cap_it_can_afford_this_turn():
    game = new_game(OPEN_RULES)
    cec = float_corp(game, "CEC")
    cec.fleets = 2
    now = planets("AMRS")  # two typed pairs: both fleets busy
    game.reachable_planets = lambda corp: now  # type: ignore[method-assign]
    action = next(a for a in game.legal_network_actions(cec) if not isinstance(a, NoNetworkAction))
    greedy = bot()
    greedy._planets_after = lambda *args: now + planets("IM", 10)  # type: ignore[method-assign]
    forecast = TrackForecast.of(game)
    reach = game.reachable(cec)
    # With 100 the build leaves 40: no third fleet, so the third pair earns nothing.
    cec.treasury = 100
    assert greedy._death_star_gains(game, forecast, cec, [action], reach) == [0]
    # With 200 it leaves 140, enough for the third fleet that runs the new pair.
    cec.treasury = 200
    assert greedy._death_star_gains(game, forecast, cec, [action], reach) == [30]


def test_a_build_that_takes_the_money_for_a_valuable_fleet_is_not_made():
    game = new_game(OPEN_RULES)
    cec = float_corp(game, "CEC")
    cec.fleets, cec.treasury = 1, 100
    now = planets("AMRS")  # a second fleet would add 30 a turn
    game.reachable_planets = lambda corp: now  # type: ignore[method-assign]
    greedy = bot()
    greedy._planets_after = lambda *args: now  # type: ignore[method-assign]
    legal = game.legal_network_actions(cec)
    assert greedy.choose_network_action(game, cec, legal) == NoNetworkAction()


# --- the construction site -------------------------------------------------------------------


def test_contract_weight_zero_never_aims_for_or_routes_through_the_site():
    game = new_game(OPEN_RULES)
    site = game.death_star_site()
    forecast = TrackForecast.of(game)
    staller = bot(contract_weight=0.0)
    assert site not in staller._death_star_targets(game, forecast, frozenset())
    assert site in staller._blocked_hexes(game)
    default = bot()
    assert default._death_star_targets(game, forecast, frozenset())[site] == 1.0
    assert site not in default._blocked_hexes(game)


def test_site_weight_is_discounted_by_how_long_the_site_will_stay():
    game = new_game()
    float_corp(game, "CEC")
    game.round_label = "OR1.1"
    contractor = bot(contract_weight=2.0)
    assert contractor._site_weight(game, TrackForecast.of(game)) == 2.0
    game.death_star.cubes = 11  # the site moves at the end of this round
    forecast = TrackForecast.of(game)
    assert forecast.site_turns_left < forecast.turns_left
    assert contractor._site_weight(game, forecast) < 2.0


def test_reserved_site_becomes_a_target_only_once_the_move_is_near():
    game = new_game(OPEN_RULES)
    float_corp(game, "CEC")
    game.round_label = "OR1.1"
    future = game.death_star_reserved_sites()[0]
    assert future not in bot()._death_star_targets(game, TrackForecast.of(game), frozenset())
    game.death_star.cubes = 11
    targets = bot()._death_star_targets(game, TrackForecast.of(game), frozenset())
    assert 0 < targets[future] < 1


def test_a_site_rushing_policy_rewards_builds_toward_the_site():
    game = new_game(OPEN_RULES)
    cec = float_corp(game, "CEC")
    cec.fleets = 1
    site = game.death_star_site()
    reach = game.reachable(cec)
    candidates = [a for a in game.legal_network_actions(cec) if not isinstance(a, NoNetworkAction)]
    forecast = TrackForecast.of(game)
    blocked = frozenset(game.death_star_reserved_sites())
    rushing = bot(contract_weight=2.0)
    bonuses = rushing._rush_bonuses(game, forecast, cec, candidates, reach, blocked)
    assert max(bonuses) > 0
    toward = max(zip(bonuses, candidates), key=lambda t: t[0])[1]
    away = min(zip(bonuses, candidates), key=lambda t: t[0])[1]
    assert toward.hex.distance(site) < away.hex.distance(site)
    assert set(bot()._rush_bonuses(game, forecast, cec, candidates, reach, blocked)) == {0.0}


def test_site_planet_is_left_out_of_planning_at_weight_zero():
    game = new_game()
    site = game.board.planet_named(SITE_NAME)
    reach = planets("R") + [site]
    kept, value = bot(contract_weight=0.0)._planning_view(game, 0.0, reach)
    assert site not in kept and value == 0
    kept, value = bot()._planning_view(game, 1.0, reach)
    assert site in kept and value == game.contract_value()


# --- shares ----------------------------------------------------------------------------------


def _fragile_kdy_game():
    game = new_game()
    float_corp(game, "CEC")
    kdy = float_corp(game, "KDY")
    kdy.fleets, kdy.treasury, kdy.last_revenue = 1, 0, 200
    game.corp("CEC").fleets = 2
    game.stock_rounds_played = 2
    seizure_next(game, round_label="SR3")
    return game


def test_bots_do_not_buy_a_corporation_that_may_close_this_round():
    game = _fragile_kdy_game()
    player = game.players[2]
    legal = game.legal_stock_actions(player, set())
    investor = bot(max_presidencies=0)
    choice = investor.choose_stock_action(game, player, legal)
    assert not (isinstance(choice, BuyShare) and choice.corp_id == "KDY")
    game.corp("KDY").treasury = 90  # it can replace its fleet now
    assert investor.choose_stock_action(game, player, legal) == BuyShare("KDY", ShareSource.IPO)


def test_sell_losers_dumps_a_fragile_corporation():
    game = _fragile_kdy_game()
    player = game.players[2]
    legal = game.legal_stock_actions(player, set())
    choice = bot(sell_losers=True).choose_stock_action(game, player, legal)
    assert choice == SellShares("KDY", 1)


def test_sell_own_before_seizure_sells_down_to_what_keeps_the_presidency():
    game = new_game()
    float_corp(game, "CEC")
    p1 = game.players[0]
    for _ in range(3):
        game.apply_stock_action(p1, BuyShare("CEC", ShareSource.IPO), set())
    assert p1.shares_in("CEC") == 5
    game.stock_rounds_played = 2
    legal = game.legal_stock_actions(p1, set())
    raider = bot(sell_own_before_seizure=True)
    choice = raider.choose_stock_action(game, p1, legal)
    assert not isinstance(choice, SellShares), "no seizure coming yet"
    seizure_next(game, round_label="SR3")
    choice = raider.choose_stock_action(game, p1, legal)
    # Player 2 holds 2, so Player 1 keeps 2 and stays president.
    assert choice == SellShares("CEC", 3)


# --- dividends -------------------------------------------------------------------------------


def test_threshold_policy_pays_when_nothing_needs_the_cash():
    game = new_game()
    cec = float_corp(game, "CEC")
    cec.fleets, cec.treasury = 2, 60
    reach = planets("AMRS")
    game.reachable_planets = lambda corp: reach  # type: ignore[method-assign]
    builder = GreedyBot(random.Random(0), STABLE["builder"])
    game.legal_network_actions = lambda corp: [NoNetworkAction()]  # type: ignore[method-assign]
    assert builder.choose_pay_dividends(game, cec, 60)


def test_threshold_policy_withholds_for_a_fleet_it_wants_but_cannot_afford():
    game = new_game()
    cec = float_corp(game, "CEC")
    cec.fleets, cec.treasury = 1, 40
    reach = planets("AMRS")
    game.reachable_planets = lambda corp: reach  # type: ignore[method-assign]
    game.legal_network_actions = lambda corp: [NoNetworkAction()]  # type: ignore[method-assign]
    builder = GreedyBot(random.Random(0), STABLE["builder"])
    assert not builder.choose_pay_dividends(game, cec, 30)
    baron = GreedyBot(random.Random(0), STABLE["baron"])
    assert baron.choose_pay_dividends(game, cec, 30)


def test_treasury_reserve_fleets_withholds_and_keeps_builds_out_of_the_chest():
    game = new_game(OPEN_RULES)
    cec = float_corp(game, "CEC")
    cec.fleets, cec.treasury = 2, 100
    saver = bot(pay_threshold=0, treasury_reserve_fleets=2.0)
    assert not saver.choose_pay_dividends(game, cec, 30)
    cec.treasury = 120
    assert (
        saver.choose_network_action(game, cec, game.legal_network_actions(cec)) == NoNetworkAction()
    )
    cec.treasury = 200
    assert saver.choose_pay_dividends(game, cec, 30)


# --- archetypes and the standard rules -------------------------------------------------------


@pytest.mark.parametrize("name", NEW_ARCHETYPES)
def test_death_star_knobs_do_not_change_play_with_the_rules_off(name):
    policy = STABLE[name]
    plain = replace(policy, **DEATH_STAR_KNOB_DEFAULTS)
    logs = []
    for p in (policy, plain):
        game = new_game(CLASSIC_CONFIG, seed=2)
        rng = random.Random(2)
        run_game(game, {pl.id: GreedyBot(random.Random(rng.random()), p) for pl in game.players})
        logs.append(_log(game))
    assert logs[0] == logs[1]


@pytest.mark.parametrize("name", NEW_ARCHETYPES)
def test_new_archetypes_play_a_death_star_game(name):
    game, _ = play_one(1, 3, name, RULES)
    assert game.is_over()
    assert any("buys a fleet" in e.text for e in game.log)


@pytest.mark.parametrize(
    "knobs",
    [
        {"fleet_payback_turns": 0},
        {"fleet_target": -1},
        {"contract_weight": -0.5},
        {"treasury_reserve_fleets": -1},
    ],
)
def test_bad_death_star_knobs_are_rejected(knobs):
    with pytest.raises(ValueError):
        GreedyPolicy(**knobs)


def test_routes_never_step_straight_between_adjacent_hubs():
    for seed in range(1, 40):
        game = new_game(OPEN_RULES, seed=seed)
        site = game.death_star_site()
        neighbours = [n for _, n in game.board.neighbors(site) if game.board.is_planet(n)]
        if neighbours:
            break
    else:
        pytest.fail("no seed puts a planet next to the site")
    cec = float_corp(game, "CEC")
    to_site = GreedyBot._route_costs(game, cec, [site], frozenset())
    # Reaching the site from its neighbour needs a lane round through another hex.
    assert to_site[neighbours[0]] >= OPEN_RULES.chart_cost


def test_contract_revenue_does_not_count_toward_a_reserve_when_the_site_moves_first():
    from bby18.revenue import RevenueResult, ScoredPair

    game = new_game()
    cec = float_corp(game, "CEC")
    site = game.board.planet_named(SITE_NAME)
    kessel, a, m = planets("RAM")
    result = RevenueResult((ScoredPair(kessel, site, 40, False, True), ScoredPair(a, m, 30, True)))
    game.revenue = lambda corp: result  # type: ignore[method-assign]
    forecast = TrackForecast(
        turns_left=10,
        site_turns_left=1,
        rounds_to_site_move=1,
        seizure_deadline=3,
        seizure_within_round=True,
        cautious_price=90,
    )
    assert GreedyBot._lasting_revenue(game, forecast, cec) == 30
    staying = replace(forecast, rounds_to_site_move=5)
    assert GreedyBot._lasting_revenue(game, staying, cec) == 70
