"""Sweep measurements of the experimental facility rules (``bby18.facility_metrics``) and the
network counts every sweep row carries (``bby18.metrics``)."""

from collections import Counter
from dataclasses import replace

import pytest

from bby18.actions import BuildFacility, BuyShare, Chart, ShareSource
from bby18.config import SEIZURE, GameConfig
from bby18.death_star_metrics import ROW_PREFIX as DS
from bby18.death_star_report import death_star_report, variant_report
from bby18.facility_metrics import (
    BUILD_EXIT_KINDS,
    OWN_LANE,
    RIVAL_LANE,
    ROW_PREFIX,
    UNCLAIMED,
    build_exit_kind,
    facility_metrics,
)
from bby18.game import EMPIRE, Game, LogEntry
from bby18.hexgrid import Direction as D
from bby18.hexgrid import Hex
from bby18.metrics import LATE_ROUND, count_log, planets_touched
from bby18.playtest import play_one
from bby18.sweep import parse_spec, run_sweep

RULES = replace(GameConfig(), facility_rules=True)
OPEN_RULES = replace(RULES, asteroid_fraction=0.0, nebula_fraction=0.0)
FLEETS = GameConfig()

CORELLIA = Hex(-5, 3)
ALDERAAN = Hex(-4, 1)
BETWEEN = Hex(-4, 2)
"""Next to Corellia (its NE side), Alderaan (SE side) and Kuat (W side)."""
WEST_OF_BETWEEN = Hex(-5, 2)
"""Next to Corellia (its NW side) and Alderaan (SW side)."""
EAST_OF_ALDERAAN = Hex(-3, 1)
"""Next to Alderaan (its E side) and Kuat (NW side)."""


def new_game(config=OPEN_RULES):
    return Game.new([f"Player {i + 1}" for i in range(3)], config, 1)


def float_corp(game, corp_id, par=60):
    p1, p2, p3 = game.players[:3]
    for player, extra in ((p1, par), (p2, 0), (p3, 0), (p2, 0)):
        game.apply_stock_action(player, BuyShare(corp_id, ShareSource.IPO, extra), set())
    return game.corp(corp_id)


def chart(game, corp, hex, *exits):
    game.apply_network_action(corp, Chart(hex, frozenset(exits), game.chart_cost(hex)))


def build(game, corp, planet, side=None):
    game.apply_fleet_action(corp, BuildFacility(planet, side, game.fleet_price()))


def corellia_and_alderaan():
    """CEC with lanes from Corellia to Alderaan, one of them dangling on Alderaan's SW side."""
    game = new_game()
    cec = float_corp(game, "CEC")
    chart(game, cec, BETWEEN, D.SW, D.NW)
    chart(game, cec, WEST_OF_BETWEEN, D.SE, D.NE)
    return game, cec


# --- counts for every rule set ----------------------------------------------------------------


def test_network_actions_are_counted_with_those_from_the_late_round_on():
    late = f"OR{LATE_ROUND}.1"
    log = [
        LogEntry("OR1.1", "CEC", "chart (-4,2) exits SW/NW for 60; claims an exit of Corellia"),
        LogEntry("OR1.2", "CEC", "takes no network action"),
        LogEntry(f"OR{LATE_ROUND - 1}.2", "CEC", "service (-3,3) for 60"),
        LogEntry(late, "CEC", "upgrade (-4,2) add E for 80"),
        LogEntry(late, "CEC", "builds a facility at Alderaan for 60 (exit unclaimed); owns 2"),
        LogEntry(late, "KDY", "chart (-3,3) exits SE/NW for 60"),
    ]
    corp = count_log(log, ["CEC", "KDY"], top_price=400, chart_cost=60).corps["CEC"]
    assert (corp.network_actions, corp.late_network_actions) == (3, 1)
    assert (corp.charts, corp.services, corp.upgrades, corp.no_network_actions) == (1, 1, 1, 1)


def test_planets_touched_count_lanes_facing_planets_even_when_they_dangle():
    game, _ = corellia_and_alderaan()
    assert game.network.dangling_sides(ALDERAAN) == {D.SW}
    assert planets_touched(game) == 2
    fleets = new_game(replace(FLEETS, asteroid_fraction=0.0, nebula_fraction=0.0))
    cec = float_corp(fleets, "CEC")
    chart(fleets, cec, BETWEEN, D.SW, D.E)
    assert planets_touched(fleets) == 2, "Corellia and Kuat, under any rules"


# --- facility measurements --------------------------------------------------------------------


def test_build_exit_kind_tells_the_builders_lane_a_rivals_and_unclaimed():
    game, cec = corellia_and_alderaan()
    kdy = float_corp(game, "KDY")
    chart(game, kdy, EAST_OF_ALDERAAN, D.SE, D.W)
    price = game.fleet_price()
    assert build_exit_kind(game, "CEC", BuildFacility(ALDERAAN, D.SW, price)) == OWN_LANE
    assert build_exit_kind(game, "CEC", BuildFacility(ALDERAAN, D.E, price)) == RIVAL_LANE
    assert build_exit_kind(game, "CEC", BuildFacility(ALDERAAN, None, price)) == UNCLAIMED
    assert build_exit_kind(game, "KDY", BuildFacility(ALDERAAN, D.E, price)) == OWN_LANE


def test_facility_metrics_read_exits_slots_and_dangling_lanes_from_the_board():
    game, cec = corellia_and_alderaan()
    build(game, cec, ALDERAAN)
    limited = sum(1 for p in game.board.planets if game.network.has_exit_limit(p.hex))
    metrics = facility_metrics(game, Counter({UNCLAIMED: 1}))
    assert metrics.home_facilities == 1 and metrics.facilities_built == 1
    assert (metrics.exits_to_own_lanes, metrics.exits_to_rival_lanes) == (0, 0)
    assert metrics.exits_left_unclaimed == 1
    assert (metrics.corporate_facilities, metrics.imperial_facilities) == (2, 0)
    assert metrics.limited_planets == limited == len(game.board.planets) - 1, "not the site"
    assert metrics.planet_exits == limited + 2
    assert metrics.planets_at_base_exits == limited - 2
    assert metrics.claimed_exits == 3, "Corellia's NE and NW, Alderaan's SE"
    assert metrics.unclaimed_exits == metrics.planet_exits - 3
    assert metrics.dangling_lanes == 1
    assert metrics.connected_planets == 2
    results = game.config.death_star_stage_results
    game.death_star.cubes = (results.index(SEIZURE) + 1) * game.config.death_star_cubes_per_stage
    game.resolve_death_star()
    seized = facility_metrics(game, Counter({UNCLAIMED: 1}))
    assert (seized.corporate_facilities, seized.imperial_facilities) == (1, 1)
    row = seized.to_row()
    assert row[f"{ROW_PREFIX}imperial_facilities"] == 1
    assert all(k.startswith(ROW_PREFIX) for k in row)


def test_facility_metrics_need_the_rules_and_known_exit_kinds():
    with pytest.raises(ValueError, match="facility_rules"):
        facility_metrics(new_game(FLEETS), Counter())
    with pytest.raises(ValueError, match="Unknown build exit kinds"):
        facility_metrics(new_game(), Counter({"sideways": 1}))


@pytest.mark.parametrize("seed", [1, 2])
def test_a_facility_game_row_agrees_with_the_finished_game(seed):
    game, summary = play_one(seed, 3, "mix:baron,early-builder,targeted", RULES)
    facilities = summary.facilities
    assert facilities is not None and summary.death_star is not None
    exits = (
        facilities.exits_to_own_lanes,
        facilities.exits_to_rival_lanes,
        facilities.exits_left_unclaimed,
    )
    assert sum(exits) == facilities.facilities_built == game.fleets_sold
    assert sum(c.fleets_bought for c in summary.death_star.corps.values()) == game.fleets_sold
    assert facilities.corporate_facilities + facilities.imperial_facilities == len(game.facilities)
    assert facilities.imperial_facilities == sum(1 for f in game.facilities if f.owner == EMPIRE)
    assert facilities.home_facilities == summary.floated + len(game.closed_corporations())
    assert facilities.planet_exits == (
        facilities.limited_planets * RULES.planet_base_exits + len(game.facilities)
    )
    assert facilities.claimed_exits + facilities.unclaimed_exits == facilities.planet_exits
    assert summary.planets_touched >= facilities.connected_planets
    row = summary.to_row()
    assert row[f"{ROW_PREFIX}facilities_built"] == game.fleets_sold
    assert row[f"{ROW_PREFIX}seizure_ties"] == game.facility_seizure_ties
    for corp in game.corporations.values():
        assert row[f"corp.{corp.id}.late_network_actions"] <= row[f"corp.{corp.id}.network_actions"]


def test_rows_without_the_facility_rules_have_no_facility_fields():
    _, summary = play_one(1, 3, "mix:baron,early-builder,targeted", FLEETS)
    row = summary.to_row()
    assert summary.facilities is None
    assert not [k for k in row if k.startswith(ROW_PREFIX)]
    assert "planets_touched" in row and "corp.CEC.network_actions" in row


# --- the report and sweeps --------------------------------------------------------------------


def _rows(config, variant, seeds, bot="mix:baron,early-builder,targeted"):
    rows = []
    for seed in seeds:
        _, summary = play_one(seed, 3, bot, config)
        rows.append({"variant": variant, "player_count": 3, "bot": bot, "seed": seed})
        rows[-1].update(summary.to_row())
    return rows


def test_report_shows_network_lines_everywhere_and_facility_lines_under_the_rules():
    rows = _rows(FLEETS, "fleets", [1]) + _rows(RULES, "facilities", [1, 2])
    facilities, fleets = death_star_report(rows).split("\n\n")
    assert facilities.startswith(
        "variant facilities: 2 games, Death Star rules on, facility rules on"
    )
    assert fleets.startswith("variant fleets: 1 games, Death Star rules on\n")
    assert "network actions per corporation that operated (6): " in facilities
    assert "network actions per corporation that operated (3): " in fleets
    for block in (facilities, fleets):
        assert f"(from round {LATE_ROUND} on " in block
        assert "planets touched by a tile per game" in block
    for phrase in [
        "facilities per corporation that operated",
        "facilities (experimental facility rules):",
        "slots filled at the end per game: corporations",
        "planets never built on (base exits only)",
        "dangling lanes",
        "new exits of built facilities: to the builder's dangling lane",
        "seizures decided by the tie-break between planets per game",
    ]:
        assert phrase in facilities, phrase
    assert "facilities" not in fleets and "fleets per corporation that operated" in fleets


def test_report_marks_network_counts_missing_from_older_rows():
    rows = _rows(FLEETS, "v", [1])
    for row in rows:
        for key in [k for k in row if k.endswith("network_actions")]:
            del row[key]
    assert "network actions per corporation that operated (3): n/a" in variant_report("v", rows)


def test_report_rejects_a_variant_mixing_facility_rules_on_and_off():
    rows = _rows(FLEETS, "v", [1]) + _rows(RULES, "v", [1])
    with pytest.raises(ValueError, match="facility rules on and off"):
        variant_report("v", rows)


def test_a_sweep_spec_variant_turns_the_facility_rules_on():
    spec = parse_spec(
        {
            "variants": {"facilities": {"facility_rules": True}, "fleets": {}},
            "seeds": [1, 1],
            "bots": ["mix:baron,early-builder,targeted"],
        }
    )
    assert spec.variants["facilities"] == RULES
    rows = run_sweep(spec.variants, spec.seeds, spec.player_counts, spec.bot_kinds, workers=1)
    by_variant = {r["variant"]: r for r in rows}
    assert by_variant["facilities"]["overrides"] == {"facility_rules": True}
    assert f"{ROW_PREFIX}facilities_built" in by_variant["facilities"]
    assert f"{DS}launched" in by_variant["facilities"]
    assert not [k for k in by_variant["fleets"] if k.startswith(ROW_PREFIX)]
    assert set(BUILD_EXIT_KINDS) == {OWN_LANE, RIVAL_LANE, UNCLAIMED}
