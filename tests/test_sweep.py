import io
import json
import pickle
from dataclasses import replace

import pytest

from bby18.board import load_board
from bby18.config import DEFAULT_CONFIG
from bby18.revenue import clear_revenue_cache, compute_revenue, compute_revenue_uncached
from bby18.sweep import (
    grid_variants,
    parse_spec,
    read_rows,
    run_sweep,
    SweepError,
    summarize,
    variant,
)


def test_variant_rejects_unknown_fields():
    with pytest.raises(ValueError, match="not_a_field"):
        variant(DEFAULT_CONFIG, not_a_field=3)


def test_variant_coerces_json_values_to_field_types():
    config = variant(
        DEFAULT_CONFIG,
        chart_cost=10,
        par_prices=[60, 70],
        regional_bonus_regions=["Core", "Mid Rim"],
        typed_pairs=[["A", "M"]],
        starting_cash_by_player_count={"3": 500},
    )
    assert config.chart_cost == 10
    assert config.par_prices == (60, 70)
    assert config.regional_bonus_regions == frozenset({"Core", "Mid Rim"})
    assert config.typed_pairs == frozenset({frozenset({"A", "M"})})
    assert config.starting_cash_by_player_count == {3: 500}
    assert DEFAULT_CONFIG.chart_cost == 60


def test_variant_rejects_wrong_value_type():
    with pytest.raises(ValueError, match="chart_cost"):
        variant(DEFAULT_CONFIG, chart_cost="cheap")


def test_config_variants_pickle_for_worker_processes():
    config = variant(DEFAULT_CONFIG, stock_market=[list(r) for r in DEFAULT_CONFIG.stock_market])
    assert config.stock_market == DEFAULT_CONFIG.stock_market
    assert pickle.loads(pickle.dumps(config)) == config


def test_grid_expands_cartesian_product_with_readable_names():
    variants = grid_variants(DEFAULT_CONFIG, {"chart_cost": [10, 30], "typed_pair_value": [25]})
    assert sorted(variants) == [
        "chart_cost=10|typed_pair_value=25",
        "chart_cost=30|typed_pair_value=25",
    ]
    assert variants["chart_cost=30|typed_pair_value=25"].chart_cost == 30


def test_parse_spec_without_grid_has_only_named_variants():
    spec = parse_spec({"variants": {"baseline": {}}, "seeds": [1, 2]})
    assert list(spec.variants) == ["baseline"]


def test_an_empty_spec_variant_plays_the_adopted_death_star_rules():
    classic = {"death_star_rules": False, "facility_rules": False}
    spec = parse_spec({"variants": {"base": {}, "classic": classic}, "seeds": [1, 2]})
    assert spec.variants["base"] == DEFAULT_CONFIG
    assert spec.variants["base"].death_star_rules and spec.variants["base"].facility_rules
    assert spec.variants["classic"] == replace(DEFAULT_CONFIG, **classic)
    spec.variants["classic"].validate_rule_variants()


def test_parse_spec_combines_named_and_grid_variants():
    spec = parse_spec(
        {
            "variants": {"baseline": {}},
            "grid": {"service_cost": [10, 20]},
            "seeds": [5, 3],
            "players": [2, 3],
            "bots": ["random"],
        }
    )
    assert sorted(spec.variants) == ["baseline", "service_cost=10", "service_cost=20"]
    assert spec.seeds == range(5, 8)
    assert spec.player_counts == [2, 3]


def _sweep(workers):
    variants = {"baseline": DEFAULT_CONFIG, "cheap": variant(DEFAULT_CONFIG, chart_cost=10)}
    out = io.StringIO()
    rows = run_sweep(variants, range(1, 3), [3], ["random"], workers=workers, out=out)
    return rows, out.getvalue()


def test_run_sweep_returns_one_row_per_game_with_metrics():
    rows, written = _sweep(workers=2)
    assert len(rows) == 4
    assert len(written.splitlines()) == 4
    assert {(r["variant"], r["seed"]) for r in rows} == {
        ("baseline", 1),
        ("baseline", 2),
        ("cheap", 1),
        ("cheap", 2),
    }
    row = rows[0]
    for key in [
        "variant",
        "overrides",
        "player_count",
        "bot",
        "seed",
        "winner",
        "winner_margin",
        "worth_cv",
        "worth.P1",
        "worth.P3",
        "corp.CEC.floated",
        "corp.CEC.par",
        "corp.CEC.final_price",
        "corp.CEC.treasury",
        "corp.CEC.revenue",
        "corp.CEC.pays",
        "corp.CEC.withholds",
        "corp.CEC.no_network_actions",
        "corp.CEC.top_price_turns",
        "final_typed_revenue",
        "final_basic_revenue",
        "ipo_buys",
        "pool_buys",
        "shares_sold",
        "planets_reached_fraction",
        "region_reached.Core",
    ]:
        assert key in row, key
    cheap = next(r for r in rows if r["variant"] == "cheap")
    assert cheap["overrides"] == {"chart_cost": 10}
    assert rows[0]["overrides"] == {}
    json.dumps(rows)


def test_parallel_and_serial_sweeps_agree():
    parallel, _ = _sweep(workers=2)
    serial, _ = _sweep(workers=1)
    strip = lambda rows: [{k: v for k, v in r.items() if k != "seconds"} for r in rows]
    assert strip(parallel) == strip(serial)


def test_run_sweep_skips_already_finished_games():
    rows = run_sweep(
        {"baseline": DEFAULT_CONFIG},
        range(1, 3),
        [3],
        ["random"],
        workers=1,
        skip=frozenset({("baseline", 3, "random", 1)}),
    )
    assert [r["seed"] for r in rows] == [2]


def test_read_rows_drops_truncated_last_line(tmp_path):
    path = tmp_path / "results.jsonl"
    path.write_text('{"a": 1}\n{"a": 2}\n{"a"', encoding="utf-8")
    assert read_rows(path) == [{"a": 1}, {"a": 2}]


def _row(variant_name, players, seed, winner, cec_floated):
    return {
        "variant": variant_name,
        "overrides": {},
        "player_count": players,
        "bot": "greedy",
        "seed": seed,
        "winner": winner,
        "worth.P1": 100,
        "worth.P2": 50,
        "corp.CEC.floated": cec_floated,
        "corp.CEC.final_price": 200 if cec_floated else 0,
    }


def test_summarize_groups_by_variant_players_and_bot():
    rows = [
        _row("a", 2, 1, "P1", True),
        _row("a", 2, 2, "P2", False),
        _row("a", 3, 1, "P1", True),
        _row("b", 2, 1, "P1", True),
    ]
    summary = summarize(rows)
    assert [(s["variant"], s["player_count"]) for s in summary] == [("a", 2), ("a", 3), ("b", 2)]
    first = summary[0]
    assert first["games"] == 2
    assert first["win_rate"] == {"P1": 0.5, "P2": 0.5}
    assert first["float_rate"] == {"CEC": 0.5}
    assert first["mean"]["corp.CEC.final_price"] == 100
    assert first["mean_when_floated"]["corp.CEC.final_price"] == 200
    assert "seed" not in first["mean"]


def test_revenue_cache_matches_uncached_under_different_configs():
    board = load_board()
    planets = list(board.planets[:10])
    rich = variant(DEFAULT_CONFIG, typed_pair_value=45, regional_bonus=5, basic_route_value=9)
    clear_revenue_cache()
    for config in (DEFAULT_CONFIG, rich, DEFAULT_CONFIG, rich):
        cached = compute_revenue(planets, config)
        assert cached == compute_revenue_uncached(planets, config)
    assert compute_revenue(planets, DEFAULT_CONFIG).total != compute_revenue(planets, rich).total


def test_revenue_does_not_depend_on_planet_order():
    board = load_board()
    planets = list(board.planets[:9])
    clear_revenue_cache()
    forward = compute_revenue(planets, DEFAULT_CONFIG)
    clear_revenue_cache()
    assert compute_revenue(list(reversed(planets)), DEFAULT_CONFIG) == forward


def test_failed_game_does_not_stop_the_sweep_but_is_reported(monkeypatch):
    import bby18.sweep as sweep_module

    real_play_one = sweep_module.play_one

    def flaky(seed, player_count, kind, config):
        if seed == 2:
            raise RuntimeError("boom")
        return real_play_one(seed, player_count, kind, config)

    monkeypatch.setattr(sweep_module, "play_one", flaky)
    with pytest.raises(SweepError, match="boom") as info:
        run_sweep({"baseline": DEFAULT_CONFIG}, range(1, 4), [3], ["random"], workers=1)
    assert [r["seed"] for r in info.value.rows] == [1, 3]
    assert [f["seed"] for f in info.value.failures] == [2]


def test_a_spec_names_corporations_by_id():
    spec = parse_spec(
        {"variants": {"four": {"corporations": ["CEC", "KDY", "CSC", "KTG"]}}, "seeds": [1, 1]}
    )
    assert [c.homeworld for c in spec.variants["four"].corporations] == [
        "Corellia",
        "Kuat",
        "Coruscant",
        "Kashyyyk",
    ]
    with pytest.raises(ValueError, match="No corporation"):
        parse_spec({"variants": {"bad": {"corporations": ["XYZ"]}}, "seeds": [1, 1]})
