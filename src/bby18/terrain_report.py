"""How much does terrain change the cost of linking planets? A map-only measurement.

No game is played. For each seed the cheapest build cost between every pair of planets is
computed on the empty sky and on the seeded sky, so the effect of asteroids and nebulae on the
routing puzzle can be read off the map alone, apart from any bot's play.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, replace
from itertools import combinations
from statistics import mean

from bby18.board import Board, Terrain, load_board
from bby18.config import GameConfig
from bby18.hexgrid import Hex
from bby18.terrain import generate_terrain

CHEAP_LINK = 150
"""A pair is "normally cheap to link" when the empty sky lets it join for under this much."""

PairCosts = dict[tuple[str, str], int]


def pair_costs(board: Board, config: GameConfig) -> PairCosts:
    """Cheapest cost to link each pair of planets, charging per space hex entered.

    Open space costs ``chart_cost`` and a nebula adds its surcharge. Planets are free to pass
    through, so a chain of planets links for the price of its gaps. Asteroid fields block.
    """

    def entry_cost(hex: Hex) -> int:
        if board.is_planet(hex):
            return 0
        extra = config.nebula_chart_surcharge if board.terrain_at(hex) is Terrain.NEBULA else 0
        return config.chart_cost + extra

    costs: PairCosts = {}
    for source in board.planets:
        dist = {source.hex: 0}
        heap = [(0, source.hex)]
        while heap:
            d, hex = heapq.heappop(heap)
            if d > dist[hex]:
                continue
            for _, nxt in board.neighbors(hex):
                nd = d + entry_cost(nxt)
                if nd < dist.get(nxt, nd + 1):
                    dist[nxt] = nd
                    heapq.heappush(heap, (nd, nxt))
        for other in board.planets:
            if source.name < other.name:
                costs[(source.name, other.name)] = dist[other.hex]
    return costs


@dataclass(frozen=True)
class SeedReport:
    seed: int
    cheap_pairs: int
    """Pairs that link for under ``CHEAP_LINK`` on the empty sky."""
    costlier_pairs: int
    """Cheap pairs that cost more under this seed's terrain."""
    mean_extra_cost: float
    """Average extra cost over the cheap pairs."""
    planet_extra: dict[str, float]
    """For each planet, the average extra cost over the cheap pairs it belongs to."""


def seed_report(seed: int, board: Board, config: GameConfig, clear_costs: PairCosts) -> SeedReport:
    terrain = generate_terrain(board, seed, config)
    costs = pair_costs(board.with_terrain(terrain), config)
    cheap = [pair for pair, cost in clear_costs.items() if cost < CHEAP_LINK]
    extra = {pair: costs[pair] - clear_costs[pair] for pair in cheap}
    per_planet: dict[str, list[int]] = {p.name: [] for p in board.planets}
    for (a, b), delta in extra.items():
        per_planet[a].append(delta)
        per_planet[b].append(delta)
    return SeedReport(
        seed=seed,
        cheap_pairs=len(cheap),
        costlier_pairs=sum(1 for d in extra.values() if d > 0),
        mean_extra_cost=mean(extra.values()) if extra else 0.0,
        planet_extra={n: mean(v) if v else 0.0 for n, v in per_planet.items()},
    )


def terrain_report(seeds: range, config: GameConfig) -> dict[str, object]:
    """Aggregate ``seed_report`` over ``seeds``."""
    board = load_board(config.map_file)
    clear = replace(config, asteroid_fraction=0.0, nebula_fraction=0.0)
    clear_costs = pair_costs(board, clear)
    reports = [seed_report(s, board, config, clear_costs) for s in seeds]
    names = [p.name for p in board.planets]
    return {
        "seeds": len(reports),
        "cheap_pairs": reports[0].cheap_pairs,
        "share_of_cheap_pairs_made_costlier": mean(
            r.costlier_pairs / r.cheap_pairs for r in reports
        ),
        "mean_extra_cost_per_cheap_pair": mean(r.mean_extra_cost for r in reports),
        "planet_mean_extra_cost": {
            n: round(mean(r.planet_extra[n] for r in reports), 1) for n in names
        },
        "planet_extra_cost_spread_across_seeds": {
            n: round(
                max(r.planet_extra[n] for r in reports) - min(r.planet_extra[n] for r in reports), 1
            )
            for n in names
        },
        "pair_count": len(list(combinations(names, 2))),
    }
