"""Supply chains and chosen surrenders (``chain_rules``)."""

import itertools
import random
from dataclasses import replace

import pytest

from bby18.actions import BuildFacility, BuyShare, ShareSource, SurrenderFacility
from bby18.board import Planet
from bby18.bots import GreedyBot
from bby18.config import DEFAULT_CONFIG, SEIZURE
from bby18.death_star import SITE_NAME
from bby18.game import EMPIRE, Game
from bby18.hexgrid import Hex
from bby18.network import IllegalAction
from bby18.playtest import play_one
from bby18.revenue import (
    EconomyKey,
    _chain_candidates,
    _score_pair,
    compute_revenue,
    compute_revenue_uncached,
)
from bby18.session import GameSession, Phase

RULES = replace(DEFAULT_CONFIG, chain_rules=True, fleet_limit=4)
OPEN_RULES = replace(RULES, asteroid_fraction=0.0, nebula_fraction=0.0)
"""Tests that place facilities run on an empty sky."""


def planet(name, tags, region="Mid Rim", q=0):
    return Planet(name, Hex(q, 0), region, frozenset(tags.split("/")))


def chains(planets, middles=(), cap=4, contract_value=0, config=RULES):
    hexes = frozenset(p.hex for p in planets if p.name in middles)
    return compute_revenue(
        planets, config, contract_value=contract_value, max_pairs=cap, middle_stops=hexes
    )


def paths(result):
    return sorted(tuple(stop.name for stop in chain.stops) for chain in result.chains)


KESSEL = planet("Kessel", "R", "Mid Rim", 0)
OUTER_KESSEL = replace(KESSEL, region="Outer Rim")
SULLUST = planet("Sullust", "I", "Mid Rim", 1)
KUAT = planet("Kuat", "S", "Core", 2)
CHANDRILA = planet("Chandrila", "M", "Core", 3)
NABOO = planet("Naboo", "A/R", "Mid Rim", 4)
SITE = planet(SITE_NAME, "W", "Outer Rim", 5)


# --- configuration -----------------------------------------------------------------------------


def test_chain_rules_require_the_facility_rules():
    with pytest.raises(ValueError, match="chain_rules requires facility_rules"):
        replace(RULES, facility_rules=False).validate_rule_variants()


def test_every_typed_pair_must_climb_the_commodity_order():
    flat = dict(RULES.commodity_order, M=1)
    with pytest.raises(ValueError, match="different rank"):
        replace(RULES, commodity_order=flat).validate_rule_variants()


def test_a_contract_must_be_worth_a_basic_route():
    with pytest.raises(ValueError, match="at least a basic route"):
        replace(RULES, death_star_stage_values=(10, 50, 60, 70)).validate_rule_variants()


# --- chains -------------------------------------------------------------------------------------


def test_a_middle_stop_needs_the_corporations_facility():
    planets = [KESSEL, SULLUST, CHANDRILA]
    without = chains(planets)
    assert without.total == 30, "one link; Chandrila is left over with nobody to pair"
    through = chains(planets, middles={"Sullust"})
    assert paths(through) == [("Kessel", "Sullust", "Chandrila")]
    assert through.total == 60
    assert [(l.a.name, l.b.name) for l in through.chains[0].links] == [
        ("Kessel", "Sullust"),
        ("Sullust", "Chandrila"),
    ]


def test_the_longest_chain_runs_from_raw_goods_to_the_station():
    planets = [KESSEL, SULLUST, KUAT, SITE]
    result = chains(planets, middles={"Sullust", "Kuat"}, contract_value=50)
    assert paths(result) == [("Kessel", "Sullust", "Kuat", SITE_NAME)]
    assert result.total == 30 + 30 + 50
    assert [l.contract for l in result.pairs] == [False, False, True]


def test_chains_only_climb():
    """Market goods go nowhere and nothing goes back to raw goods, so a facility at a market
    or a raw-goods world never makes it a middle stop."""
    farm = planet("Dantooine", "A", q=6)
    market = planet("Chandrila", "M", q=7)
    other_farm = planet("Felucia", "A", q=8)
    result = chains([farm, market, other_farm], middles={"Chandrila", "Dantooine"})
    assert result.total == 30 + 0, "one A->M link; the second farm finds no partner"
    assert all(len(chain.stops) == 2 for chain in result.chains)


def test_no_planet_is_in_two_chains():
    """Sullust could feed both Chandrila and Kuat, but only as one chain's middle stop."""
    planets = [KESSEL, SULLUST, KUAT, CHANDRILA]
    result = chains(planets, middles={"Sullust"})
    stops = [stop.name for chain in result.chains for stop in chain.stops]
    assert len(stops) == len(set(stops))
    assert result.total == 30 + 30, "Kessel->Sullust->one of them; the other has no partner"


def test_one_chain_per_facility():
    planets = [KESSEL, SULLUST, CHANDRILA, NABOO, KUAT]
    assert len(chains(planets, middles={"Sullust"}, cap=1).chains) == 1
    assert chains(planets, middles={"Sullust"}, cap=1).total == 60


def test_the_regional_bonus_is_earned_once_per_chain():
    planets = [OUTER_KESSEL, SULLUST, CHANDRILA]
    result = chains(planets, middles={"Sullust"})
    assert result.chains[0].regional == RULES.regional_bonus
    assert result.total == 30 + 30 + RULES.regional_bonus


def test_a_chain_into_the_station_earns_the_bonus_from_its_last_stop_short_of_the_site():
    core_works = planet("Kuat", "I", "Core", 2)
    result = chains([OUTER_KESSEL, core_works, SITE], middles={"Kuat"}, contract_value=50)
    assert paths(result) == [("Kessel", "Kuat", SITE_NAME)]
    assert result.total == 30 + 50 + RULES.regional_bonus
    direct = chains([OUTER_KESSEL, SITE], contract_value=50)
    assert direct.total == 50, "a contract alone never earns the regional bonus"


def test_planet_pair_bonus_counts_on_every_link_but_contracts():
    coruscant = planet("Coruscant", "M", "Core", 9)
    result = chains([OUTER_KESSEL, SULLUST, coruscant], middles={"Sullust"})
    bonus = RULES.planet_pair_bonus["Coruscant"]
    assert result.total == 30 + 30 + bonus + RULES.regional_bonus


def test_leftover_chains_are_filled_with_basic_routes():
    farm = planet("Dantooine", "A", q=6)
    result = chains([KESSEL, SULLUST, farm, NABOO], cap=3)
    assert result.total == 30 + 5
    basic = [c for c in result.chains if not c.links[0].typed]
    assert len(basic) == 1 and len(basic[0].stops) == 2


def test_middle_stops_are_part_of_the_memo_key():
    planets = [KESSEL, SULLUST, CHANDRILA]
    assert chains(planets).total == 30
    assert chains(planets, middles={"Sullust"}).total == 60
    assert chains(planets).total == 30


def test_the_pair_rules_ignore_middle_stops():
    pair_rules = replace(RULES, chain_rules=False)
    planets = [KESSEL, SULLUST, CHANDRILA]
    plain = chains(planets, config=pair_rules)
    assert chains(planets, middles={"Sullust"}, config=pair_rules) == plain
    assert plain.chains == ()


def _brute_force(planets, middles, cap, contract_value):
    """Best total over every set of at most ``cap`` planet-disjoint chains and basic routes."""
    economy = EconomyKey.of(RULES, contract_value)
    canonical = tuple(sorted(planets, key=lambda p: (p.hex, p.name)))
    options = [(c.mask, c.chain.value) for c in _chain_candidates(canonical, economy, middles)]
    for i, j in itertools.combinations(range(len(canonical)), 2):
        value, typed, contract = _score_pair(canonical[i], canonical[j], economy)
        if not typed and not contract:
            options.append(((1 << i) | (1 << j), value))
    best = 0

    def search(start, used, value, left):
        nonlocal best
        best = max(best, value)
        if left == 0:
            return
        for k in range(start, len(options)):
            mask, worth = options[k]
            if not mask & used:
                search(k + 1, used | mask, value + worth, left - 1)

    search(0, 0, 0, cap)
    return best


@pytest.mark.parametrize("seed", range(8))
def test_the_chain_search_equals_brute_force(seed):
    rng = random.Random(seed)
    tags = ["A", "R", "I", "M", "S", "I/S", "A/R"]
    regions = ["Core", "Outer Rim", "Mid Rim"]
    for _ in range(40):
        count = rng.randint(2, 8)
        planets = []
        for i in range(count):
            name = "Coruscant" if i == 0 and rng.random() < 0.3 else f"P{i}"
            planets.append(Planet(name, Hex(i, 0), rng.choice(regions), frozenset()))
            planets[-1] = replace(planets[-1], tags=frozenset(rng.choice(tags).split("/")))
        with_site = rng.random() < 0.5
        if with_site:
            planets.append(Planet(SITE_NAME, Hex(count, 0), "Outer Rim", frozenset({"W"})))
        contract_value = rng.choice([50, 80]) if with_site else 0
        middles = frozenset(p.hex for p in planets if rng.random() < 0.4)
        cap = rng.randint(1, 4)
        result = compute_revenue_uncached(
            planets, RULES, contract_value=contract_value, max_pairs=cap, middle_stops=middles
        )
        assert result.total == _brute_force(planets, middles, cap, contract_value)
        assert len(result.chains) <= cap


# --- the game -----------------------------------------------------------------------------------


def new_game(config=OPEN_RULES, seed=1):
    return Game.new([f"Player {i + 1}" for i in range(3)], config, seed)


def float_corp(game, corp_id, par=60):
    p1, p2, p3 = game.players[:3]
    for player, extra in ((p1, par), (p2, 0), (p3, 0), (p2, 0)):
        game.apply_stock_action(player, BuyShare(corp_id, ShareSource.IPO, extra), set())
    return game.corp(corp_id)


def place_facility(game, corp, planet_hex):
    """Build a facility where a test needs one, pretending ``corp`` reaches the planet."""
    real = game.reachable
    game.reachable = lambda c: real(c) | {planet_hex} if c is corp else real(c)
    game.apply_fleet_action(corp, BuildFacility(planet_hex, None, game.fleet_price()))
    game.reachable = real


def fill_through_seizure(game):
    results = game.config.death_star_stage_results
    index = results.index(SEIZURE, game.death_star_stage())
    game.death_star.cubes = (index + 1) * game.config.death_star_cubes_per_stage
    game.resolve_death_star()


def test_middle_stops_are_the_corporations_facility_planets():
    game = new_game()
    cec = float_corp(game, "CEC")
    assert game.middle_stops(cec) == {game.homeworld(cec)}
    assert new_game(replace(OPEN_RULES, chain_rules=False)).middle_stops(cec) == frozenset()


def test_a_seizure_waits_for_each_corporation_to_choose_what_it_surrenders():
    game = new_game()
    cec = float_corp(game, "CEC")
    kdy = float_corp(game, "KDY")
    other = next(
        p.hex
        for p in game.board.planets
        if game.network.has_exit_limit(p.hex)
        and p.hex not in (game.homeworld(cec),)
        and game.free_facility_slots(p.hex) > 0
    )
    place_facility(game, cec, other)
    stage = game.death_star_stage()
    fill_through_seizure(game)
    assert game.death_star_stage() == stage + 1
    queue = [c.id for c in game.operating_order() if c.id in ("CEC", "KDY")]
    assert game.surrender_queue == queue
    with pytest.raises(ValueError, match="waiting"):
        game.resolve_death_star()
    first = game.corp(queue[0])
    assert game.legal_surrenders(game.corp(queue[1])) == []
    choice = game.legal_surrenders(first)[-1]
    game.surrender_facility(first, choice)
    assert [f.owner for f in game.facilities_on(choice.planet)][-1] == EMPIRE
    with pytest.raises(IllegalAction):
        game.surrender_facility(first, choice)
    second = game.corp(queue[1])
    game.surrender_facility(second, game.legal_surrenders(second)[0])
    assert game.surrender_queue == []
    assert cec.fleets == len(game.facilities_of(cec)) == 1
    assert kdy.fleets == 0


def test_cec_chooses_between_its_two_facility_planets():
    game = new_game()
    cec = float_corp(game, "CEC")
    home = game.homeworld(cec)
    other = next(
        p.hex
        for p in game.board.planets
        if game.network.has_exit_limit(p.hex) and p.hex != home and game.free_facility_slots(p.hex)
    )
    place_facility(game, cec, other)
    fill_through_seizure(game)
    assert game.legal_surrenders(cec) == sorted(
        [SurrenderFacility(home), SurrenderFacility(other)], key=lambda a: a.planet
    )


def test_greedy_surrenders_the_facility_that_costs_least():
    game = new_game()
    cec = float_corp(game, "CEC")
    home = game.homeworld(cec)
    other = next(
        p.hex
        for p in game.board.planets
        if game.network.has_exit_limit(p.hex) and p.hex != home and game.free_facility_slots(p.hex)
    )
    place_facility(game, cec, other)
    fill_through_seizure(game)
    legal = game.legal_surrenders(cec)
    pick = GreedyBot(random.Random(1)).choose_surrender(game, cec, legal)
    assert pick in legal
    # Neither facility carries a chain yet (CEC reaches only its homeworld), so the tie goes to
    # the one farther from home.
    assert pick == SurrenderFacility(other)


@pytest.mark.parametrize("kind,seed", [("baron@site", 1), ("random", 2), ("admiral@site", 3)])
def test_bot_games_under_chain_rules_run_to_the_end(kind, seed):
    game, summary = play_one(seed, 3, kind, RULES)
    assert game.is_over()
    assert game.surrender_queue == []
    for corp in game.corporations.values():
        assert corp.fleets == len(game.facilities_of(corp)) <= RULES.fleet_limit
        for chain in game.revenue(corp).chains if corp.floated else ():
            for stop in chain.stops[1:-1]:
                assert stop.hex in game.middle_stops(corp)
    assert summary.chains is not None and summary.death_star is not None
    imperial = sum(1 for f in game.facilities if f.owner == EMPIRE)
    assert summary.chains.surrenders == imperial
    assert sum(m.fleets_seized for m in summary.death_star.corps.values()) == imperial


def test_a_session_runs_a_surrender_phase_and_resumes_play():
    game = new_game(RULES, seed=3)
    rng = random.Random(3)
    bots = {p.id: GreedyBot(random.Random(rng.random())) for p in game.players[1:]}
    session = GameSession(game, bots)
    human = GreedyBot(random.Random(5))
    saw_surrender = False
    while session.phase is not Phase.GAME_OVER:
        legal = session.legal_actions()
        corp = session.current_corporation if session.phase is not Phase.STOCK else None
        if session.phase is Phase.SURRENDER:
            saw_surrender = True
            assert corp is not None and corp.id == game.surrender_queue[0]
            session.apply(human.choose_surrender(game, corp, legal))
        elif session.phase is Phase.STOCK:
            session.apply(human.choose_stock_action(game, session.current_player, legal))
        elif session.phase is Phase.NETWORK:
            session.apply(human.choose_network_action(game, corp, legal))
        elif session.phase is Phase.FLEET:
            session.apply(human.choose_fleet_action(game, corp, legal))
        else:
            revenue = game.revenue(corp).total
            pay = revenue > 0 and human.choose_pay_dividends(game, corp, revenue)
            session.apply(legal[0] if pay else legal[-1])
    assert saw_surrender
