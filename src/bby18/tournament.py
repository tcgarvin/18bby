"""Strategy tournaments: every table of strategies from a stable, every seat order, common seeds.

A tournament plays each multiset of ``player_count`` strategies in every distinct seat order on
the same seeds, so seat advantage and the sky cancel out. A strategy's payoff at a table is its
**worth share**: its final worth over the table's total (a fair share is ``1 / player_count``).

The analysis treats the results as a symmetric game. ``payoffs[lineup][strategy]`` is the mean
share of ``strategy`` at the table ``lineup`` (a sorted tuple). From that it finds:

- **best responses:** for each set of opponents, which strategy earns most against them. A
  strategy that is the best response to nearly every opponent set dominates.
- **equilibria:** replicator dynamics from several starting mixes. Strategies left with a
  meaningful share of the population are the viable ones; the balance goal is at least two.

Seeds are resampled (bootstrap) to show how much of that is noise.
"""

from __future__ import annotations

import itertools
import math
import random
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from statistics import mean, stdev
from typing import Any

from bby18.playtest import MIX_PREFIX, seat_kinds

Row = dict[str, Any]
Lineup = tuple[str, ...]
"""A table of strategies, sorted, one entry per seat."""
Payoffs = dict[Lineup, dict[str, float]]

VIABLE_SHARE = 0.05
"""Population share above which a strategy counts as surviving in an equilibrium."""


# --- building the tournament --------------------------------------------------------------


def lineups(strategies: Sequence[str], player_count: int) -> list[Lineup]:
    """Every table of ``player_count`` strategies, repeats allowed, each sorted."""
    return [
        tuple(c) for c in itertools.combinations_with_replacement(sorted(strategies), player_count)
    ]


def seat_orders(lineup: Lineup) -> list[Lineup]:
    """The distinct seatings of ``lineup``, in a fixed order."""
    return sorted(set(itertools.permutations(lineup)))


def mix_string(seating: Lineup) -> str:
    return MIX_PREFIX + ",".join(seating)


def tournament_bots(strategies: Sequence[str], player_count: int) -> list[str]:
    """The bot strings for a full tournament: every lineup in every distinct seating."""
    if len(set(strategies)) != len(strategies):
        raise ValueError("Strategies must be distinct")
    return [
        mix_string(s) for lineup in lineups(strategies, player_count) for s in seat_orders(lineup)
    ]


# --- reading results ----------------------------------------------------------------------


@dataclass(frozen=True)
class TableResult:
    """One game, reduced to who sat where and how they did."""

    seed: int
    seating: Lineup
    shares: tuple[float, ...]
    winner_seat: int

    @property
    def lineup(self) -> Lineup:
        return tuple(sorted(self.seating))


def table_results(rows: Iterable[Row]) -> list[TableResult]:
    """Reduce sweep rows from tournament bot strings to per-seat worth shares."""
    results: list[TableResult] = []
    for row in rows:
        bot = str(row["bot"])
        if not bot.startswith(MIX_PREFIX):
            raise ValueError(f"Row bot {bot!r} is not a tournament seating")
        count = int(row["player_count"])
        seating = tuple(seat_kinds(bot, count))
        worth = [float(row[f"worth.P{i + 1}"]) for i in range(count)]
        total = sum(worth)
        if total <= 0:
            raise ValueError(f"Game with seed {row['seed']} has no worth at all")
        winner = str(row["winner"])
        results.append(
            TableResult(
                seed=int(row["seed"]),
                seating=seating,
                shares=tuple(w / total for w in worth),
                winner_seat=int(winner.removeprefix("P")) - 1,
            )
        )
    return results


def payoff_table(results: Iterable[TableResult]) -> Payoffs:
    """Mean worth share of each strategy at each lineup, pooled over seats and seeds.

    A strategy that fills two seats at a table is averaged over both seats.
    """
    sums: dict[Lineup, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for result in results:
        for kind, share in zip(result.seating, result.shares):
            sums[result.lineup][kind].append(share)
    return {lineup: {k: mean(v) for k, v in by_kind.items()} for lineup, by_kind in sums.items()}


def win_rates(results: Iterable[TableResult]) -> dict[str, float]:
    """Each strategy's share of the seats it filled that won, over all tables."""
    seats: dict[str, int] = defaultdict(int)
    wins: dict[str, int] = defaultdict(int)
    for result in results:
        for i, kind in enumerate(result.seating):
            seats[kind] += 1
            wins[kind] += i == result.winner_seat
    return {k: wins[k] / seats[k] for k in seats}


def strategies_in(payoffs: Payoffs) -> list[str]:
    return sorted({k for lineup in payoffs for k in lineup})


def check_complete(payoffs: Payoffs, strategies: Sequence[str], player_count: int) -> None:
    missing = [lu for lu in lineups(strategies, player_count) if lu not in payoffs]
    if missing:
        raise ValueError(f"{len(missing)} lineups have no games, e.g. {missing[0]}")


# --- analysis -----------------------------------------------------------------------------


def payoff(payoffs: Payoffs, strategy: str, opponents: Sequence[str]) -> float:
    return payoffs[tuple(sorted((strategy, *opponents)))][strategy]


def best_responses(payoffs: Payoffs, player_count: int) -> dict[Lineup, str]:
    """For each set of opponents (sorted), the strategy with the highest share against it."""
    strategies = strategies_in(payoffs)
    return {
        opponents: max(strategies, key=lambda s: payoff(payoffs, s, opponents))
        for opponents in lineups(strategies, player_count - 1)
    }


class SymmetricGame:
    """A payoff table laid out for fast fitness sums: one row per strategy, one column per
    ordered tuple of opponents."""

    def __init__(self, payoffs: Payoffs, player_count: int) -> None:
        self.strategies = strategies_in(payoffs)
        check_complete(payoffs, self.strategies, player_count)
        index = range(len(self.strategies))
        self.columns = list(itertools.product(index, repeat=player_count - 1))
        self.rows = [
            [payoff(payoffs, s, [self.strategies[o] for o in column]) for column in self.columns]
            for s in self.strategies
        ]

    def fitness(self, population: Sequence[float]) -> list[float]:
        """Expected share of each strategy when opponents are drawn from ``population``."""
        weights = [math.prod(population[o] for o in column) for column in self.columns]
        return [sum(p * w for p, w in zip(row, weights)) for row in self.rows]


def fitness(
    payoffs: Payoffs, population: Mapping[str, float], player_count: int
) -> dict[str, float]:
    """Expected share of each strategy when its opponents are drawn from ``population``."""
    game = SymmetricGame(payoffs, player_count)
    values = game.fitness([population[s] for s in game.strategies])
    return dict(zip(game.strategies, values))


def replicator(
    payoffs: Payoffs,
    player_count: int,
    start: Mapping[str, float] | None = None,
    steps: int = 20000,
    rate: float = 30.0,
    tolerance: float = 1e-10,
) -> dict[str, float]:
    """The population mix that exponential replicator dynamics settle on from ``start``.

    Each step multiplies a strategy's share by ``exp(rate * (fitness - mean fitness))``. Shares
    are worth shares, so differences are a few hundredths and ``rate`` is correspondingly large.
    ``start`` defaults to the uniform mix. Stops early once no share moves by ``tolerance``.
    """
    game = SymmetricGame(payoffs, player_count)
    strategies = game.strategies
    if start is None:
        population = [1.0 / len(strategies)] * len(strategies)
    else:
        total = sum(start.values())
        population = [start.get(s, 0.0) / total for s in strategies]
    for _ in range(steps):
        fit = game.fitness(population)
        average = sum(p * f for p, f in zip(population, fit))
        grown = [p * math.exp(rate * (f - average)) for p, f in zip(population, fit)]
        total = sum(grown)
        updated = [g / total for g in grown]
        moved = max(abs(u - p) for u, p in zip(updated, population))
        population = updated
        if moved < tolerance:
            break
    return dict(zip(strategies, population))


def survivors(population: Mapping[str, float], threshold: float = VIABLE_SHARE) -> list[str]:
    return sorted(
        (s for s, v in population.items() if v >= threshold), key=lambda s: -population[s]
    )


def random_starts(
    strategies: Sequence[str], count: int, rng: random.Random
) -> list[dict[str, float]]:
    """Uniform plus ``count - 1`` random (Dirichlet(1)) starting mixes."""
    starts = [{s: 1.0 for s in strategies}]
    for _ in range(count - 1):
        starts.append({s: rng.expovariate(1.0) for s in strategies})
    return starts


def invasion_cells(
    results: Iterable[TableResult], player_count: int
) -> dict[tuple[str, str], tuple[float, float]]:
    """``(invader, resident) -> (mean share, standard error)`` for one invader seated with
    ``player_count - 1`` copies of the resident. The error treats each game as independent."""
    shares: dict[tuple[str, str], list[float]] = defaultdict(list)
    for result in results:
        kinds = set(result.seating)
        if len(kinds) != 2:
            continue
        for i, kind in enumerate(result.seating):
            if result.seating.count(kind) == 1:
                resident = next(k for k in kinds if k != kind)
                shares[(kind, resident)].append(result.shares[i])
    cells: dict[tuple[str, str], tuple[float, float]] = {}
    for key, values in shares.items():
        error = stdev(values) / math.sqrt(len(values)) if len(values) > 1 else math.inf
        cells[key] = (mean(values), error)
    return cells


def bootstrap(results: Sequence[TableResult], rng: random.Random) -> list[TableResult]:
    """Resample seeds with replacement, keeping every table played on a chosen seed."""
    by_seed: dict[int, list[TableResult]] = defaultdict(list)
    for result in results:
        by_seed[result.seed].append(result)
    seeds = sorted(by_seed)
    return [r for seed in rng.choices(seeds, k=len(seeds)) for r in by_seed[seed]]


# --- report -------------------------------------------------------------------------------


def report(
    results: Sequence[TableResult],
    player_count: int,
    bootstrap_runs: int = 40,
    starts: int = 6,
    seed: int = 0,
) -> str:
    """A text report: overall shares, invasion matrix, best responses, equilibria."""
    rng = random.Random(seed)
    payoffs = payoff_table(results)
    strategies = strategies_in(payoffs)
    check_complete(payoffs, strategies, player_count)
    fair = 1.0 / player_count
    lines = [
        f"{len(results)} games, {len(strategies)} strategies, {player_count} players, "
        f"{len({r.seed for r in results})} seeds",
        "",
        "Mean share over all tables (fair = {:.1f}%) and win rate:".format(100 * fair),
    ]
    uniform = fitness(payoffs, {s: 1.0 / len(strategies) for s in strategies}, player_count)
    wins = win_rates(results)
    for s in sorted(strategies, key=lambda s: -uniform[s]):
        lines.append(f"  {s:<16} {100 * uniform[s]:5.1f}%   wins {100 * wins[s]:5.1f}%")

    lines += ["", "Invasion: share of one row strategy against all-column opponents (%):"]
    width = max(len(s) for s in strategies)
    lines.append(" " * (width + 2) + " ".join(f"{s[:6]:>6}" for s in strategies))
    for x in strategies:
        cells = [100 * payoff(payoffs, x, (y,) * (player_count - 1)) for y in strategies]
        lines.append(f"  {x:<{width}}" + " ".join(f"{c:6.1f}" for c in cells))

    lines += [
        "",
        "Invasions clearly above a fair share (mean - 2 standard errors > fair; the diagonal and",
        "strategies that invade nothing are omitted):",
    ]
    invasions = invasion_cells(results, player_count)
    for x in strategies:
        clear = [
            f"{y} {100 * m:.1f}±{100 * se:.1f}"
            for y in strategies
            if y != x
            for m, se in [invasions[(x, y)]]
            if m - 2 * se > fair
        ]
        if clear:
            lines.append(f"  {x:<{width}} invades {', '.join(clear)}")

    responses = best_responses(payoffs, player_count)
    counts: dict[str, int] = defaultdict(int)
    for best in responses.values():
        counts[best] += 1
    lines += ["", f"Best response counts over {len(responses)} opponent sets:"]
    for s, n in sorted(counts.items(), key=lambda t: -t[1]):
        lines.append(f"  {s:<16} {n}")

    lines += ["", "Equilibria (replicator dynamics, share >= {:.0f}%):".format(100 * VIABLE_SHARE)]
    seen: set[tuple[str, ...]] = set()
    for start in random_starts(strategies, starts, rng):
        population = replicator(payoffs, player_count, start)
        support = tuple(survivors(population))
        if support in seen:
            continue
        seen.add(support)
        mix = ", ".join(f"{s} {100 * population[s]:.0f}%" for s in support)
        lines.append(f"  {len(support)} viable: {mix}")

    if bootstrap_runs:
        support_sizes: list[int] = []
        survived: dict[str, int] = defaultdict(int)
        top: dict[str, int] = defaultdict(int)
        for _ in range(bootstrap_runs):
            sample = payoff_table(bootstrap(results, rng))
            population = replicator(sample, player_count)
            alive = survivors(population)
            support_sizes.append(len(alive))
            for s in alive:
                survived[s] += 1
            top[max(population, key=lambda s: population[s])] += 1
        lines += [
            "",
            f"Bootstrap over seeds ({bootstrap_runs} runs, uniform start): "
            f"viable count mean {mean(support_sizes):.1f}, "
            f"min {min(support_sizes)}, max {max(support_sizes)}",
        ]
        for s in sorted(strategies, key=lambda s: -survived[s]):
            if survived[s]:
                lines.append(
                    f"  {s:<16} survives {100 * survived[s] / bootstrap_runs:3.0f}%  "
                    f"largest {100 * top[s] / bootstrap_runs:3.0f}%"
                )
    return "\n".join(lines)
