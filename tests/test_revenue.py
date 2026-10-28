from dataclasses import replace

from bby18.board import Planet
from bby18.config import DEFAULT_CONFIG as CFG
from bby18.hexgrid import Hex
from bby18.revenue import compute_revenue, pair_value


def planet(name, tags, region="Mid Rim"):
    return Planet(name, Hex(0, 0), region, frozenset(tags))


def test_typed_pairs_earn_flat_value():
    assert pair_value(planet("a", "A"), planet("m", "M"), CFG) == (30, True)
    assert pair_value(planet("r", "R"), planet("s", "S"), CFG) == (30, True)


def test_untyped_pair_is_basic_route():
    assert pair_value(planet("a", "A"), planet("r", "R"), CFG) == (5, False)
    assert pair_value(planet("m", "M"), planet("m2", "M"), CFG) == (5, False)


def test_core_outer_rim_bonus_only_for_typed_pairs():
    core = planet("core", "M", "Core")
    outer_ag = planet("outer", "A", "Outer Rim")
    outer_res = planet("outer2", "R", "Outer Rim")
    assert pair_value(core, outer_ag, CFG) == (50, True)
    assert pair_value(core, outer_res, CFG) == (5, False)


def test_dual_tag_uses_best_tag_but_scores_once():
    corellia = planet("Corellia", "IS", "Core")
    kuat = planet("Kuat", "S", "Core")
    kashyyyk = planet("Kashyyyk", "R")
    result = compute_revenue([corellia, kuat, kashyyyk], CFG)
    # Best: Corellia(I)<->Kuat(S) 30 or Corellia(S)<->Kashyyyk(R) 30; either way one pair of 30
    # plus nothing (odd planet count). Total must be 30.
    assert result.total == 30
    assert len(result.pairs) == 1


def test_matching_prefers_typed_pairs_over_basic_routes():
    a = planet("ag", "A")
    m = planet("mk", "M")
    r = planet("rs", "R")
    i = planet("in", "I")
    result = compute_revenue([a, m, r, i], CFG)
    assert result.total == 60
    assert all(p.typed for p in result.pairs)


def test_leftover_planets_form_basic_routes():
    result = compute_revenue([planet("a1", "A"), planet("a2", "A")], CFG)
    assert result.total == 5
    assert not result.pairs[0].typed


def test_single_planet_earns_nothing():
    assert compute_revenue([planet("solo", "M")], CFG).total == 0


def test_planet_pair_bonus_adds_to_typed_and_basic_pairs_with_that_planet():
    bonus = replace(CFG, planet_pair_bonus={"a": 10})
    assert pair_value(planet("a", "A"), planet("m", "M"), bonus) == (40, True)
    assert pair_value(planet("a", "A"), planet("r", "R"), bonus) == (15, False)
    assert pair_value(planet("r", "R"), planet("s", "S"), bonus) == (30, True)


def test_coruscant_pairs_pay_ten_more_by_default():
    assert CFG.planet_pair_bonus == {"Coruscant": 10}
