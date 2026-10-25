import random

import pytest

from bby18.sweep import parse_spec
from bby18.tournament import (
    TableResult,
    best_responses,
    bootstrap,
    invasion_cells,
    lineups,
    payoff_table,
    replicator,
    seat_orders,
    survivors,
    table_results,
    tournament_bots,
    win_rates,
)


def test_lineups_are_sorted_multisets():
    assert lineups(["b", "a"], 2) == [("a", "a"), ("a", "b"), ("b", "b")]


def test_seat_orders_are_distinct_permutations():
    assert seat_orders(("a", "a", "b")) == [("a", "a", "b"), ("a", "b", "a"), ("b", "a", "a")]
    assert len(seat_orders(("a", "b", "c"))) == 6
    assert seat_orders(("a", "a", "a")) == [("a", "a", "a")]


def test_tournament_bots_cover_every_seating_once():
    bots = tournament_bots(["x", "y"], 3)
    # xxx, yyy, and three seatings each of xxy and xyy.
    assert len(bots) == 8 == len(set(bots))
    assert "mix:y,x,x" in bots


def test_tournament_bots_reject_repeated_strategies():
    with pytest.raises(ValueError):
        tournament_bots(["x", "x"], 3)


def test_parse_spec_expands_a_tournament_into_seatings():
    spec = parse_spec(
        {"variants": {"base": {}}, "seeds": [1, 2], "tournament": ["baron", "builder"]}
    )
    assert len(spec.bot_kinds) == 8


def test_parse_spec_rejects_tournament_over_several_player_counts():
    with pytest.raises(ValueError):
        parse_spec(
            {"variants": {"b": {}}, "seeds": [1, 1], "players": [3, 4], "tournament": ["baron"]}
        )


def test_table_results_turn_worth_into_shares():
    row = {
        "bot": "mix:baron,builder,baron",
        "player_count": 3,
        "seed": 4,
        "winner": "P2",
        "worth.P1": 100,
        "worth.P2": 200,
        "worth.P3": 100,
    }
    [result] = table_results([row])
    assert result.seating == ("baron", "builder", "baron")
    assert result.shares == (0.25, 0.5, 0.25)
    assert result.winner_seat == 1
    assert result.lineup == ("baron", "baron", "builder")


def _game(seating: tuple[str, ...], shares: tuple[float, ...], seed: int = 1) -> TableResult:
    winner = max(range(len(shares)), key=lambda i: shares[i])
    return TableResult(seed=seed, seating=seating, shares=shares, winner_seat=winner)


def test_payoff_table_averages_a_strategy_over_its_seats():
    payoffs = payoff_table([_game(("a", "a", "b"), (0.2, 0.4, 0.4))])
    assert payoffs[("a", "a", "b")] == {"a": pytest.approx(0.3), "b": pytest.approx(0.4)}


def test_win_rates_count_seats_not_tables():
    rates = win_rates([_game(("a", "a", "b"), (0.5, 0.2, 0.3))])
    assert rates == {"a": 0.5, "b": 0.0}


def _two_strategy_game(rare_bonus: float, a_edge: float) -> list[TableResult]:
    """Two strategies; a lone strategy earns ``rare_bonus`` above a fair share, and ``a``
    earns ``a_edge`` extra everywhere (taken evenly from the others)."""
    third = 1 / 3

    def shares(seating: tuple[str, ...]) -> tuple[float, ...]:
        counts = {k: seating.count(k) for k in seating}
        base = [
            third + (rare_bonus if counts[k] == 1 and len(counts) > 1 else 0.0) for k in seating
        ]
        base = [b + (a_edge if k == "a" else 0.0) for b, k in zip(base, seating)]
        total = sum(base)
        return tuple(b / total for b in base)

    return [_game(s, shares(s)) for lu in lineups(["a", "b"], 3) for s in seat_orders(lu)]


def test_replicator_keeps_both_strategies_when_each_does_better_when_rare():
    payoffs = payoff_table(_two_strategy_game(rare_bonus=0.1, a_edge=0.0))
    population = replicator(payoffs, 3)
    assert survivors(population) and len(survivors(population)) == 2
    assert population["a"] == pytest.approx(0.5, abs=0.01)


def test_replicator_converges_on_a_dominant_strategy():
    payoffs = payoff_table(_two_strategy_game(rare_bonus=0.0, a_edge=0.05))
    assert survivors(replicator(payoffs, 3)) == ["a"]


def test_best_responses_name_the_dominant_strategy_everywhere():
    payoffs = payoff_table(_two_strategy_game(rare_bonus=0.0, a_edge=0.05))
    assert set(best_responses(payoffs, 3).values()) == {"a"}


def test_bootstrap_keeps_whole_seeds():
    results = [_game(("a", "b", "b"), (0.4, 0.3, 0.3), seed=s) for s in (1, 1, 2)]
    sample = bootstrap(results, random.Random(0))
    by_seed = {r.seed for r in sample}
    for seed in by_seed:
        assert sum(r.seed == seed for r in sample) % sum(r.seed == seed for r in results) == 0


def test_invasion_cells_pool_the_lone_strategy_over_games():
    results = [
        _game(("a", "b", "b"), (0.5, 0.25, 0.25), seed=1),
        _game(("b", "a", "b"), (0.2, 0.3, 0.5), seed=2),
        _game(("a", "b", "c"), (0.4, 0.3, 0.3), seed=1),
    ]
    cells = invasion_cells(results, 3)
    assert cells[("a", "b")][0] == pytest.approx(0.4)
    assert cells[("a", "b")][1] == pytest.approx(0.1)
    assert ("a", "c") not in cells
