"""Planet-pair revenue: a maximum-weight matching over a corporation's reachable planets."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import networkx as nx

from bby18.board import Planet
from bby18.config import GameConfig


@dataclass(frozen=True)
class ScoredPair:
    a: Planet
    b: Planet
    value: int
    typed: bool

    def __str__(self) -> str:
        kind = "typed" if self.typed else "basic"
        return f"{self.a.name} <-> {self.b.name} ({kind} {self.value})"


@dataclass(frozen=True)
class RevenueResult:
    pairs: tuple[ScoredPair, ...]

    @property
    def total(self) -> int:
        return sum(p.value for p in self.pairs)


def pair_value(a: Planet, b: Planet, config: GameConfig) -> tuple[int, bool]:
    """Best value of pairing two planets and whether that pairing is a typed one."""
    typed = any(frozenset({ta, tb}) in config.typed_pairs for ta in a.tags for tb in b.tags)
    if not typed:
        return config.basic_route_value, False
    value = config.typed_pair_value
    if {a.region, b.region} == set(config.regional_bonus_regions):
        value += config.regional_bonus
    return value, True


def compute_revenue(planets: list[Planet], config: GameConfig) -> RevenueResult:
    """Optimal non-overlapping pairing of the given mutually reachable planets."""
    graph: nx.Graph[str] = nx.Graph()
    for a, b in combinations(planets, 2):
        value, typed = pair_value(a, b, config)
        graph.add_edge(a.name, b.name, weight=value, typed=typed)
    matching = nx.max_weight_matching(graph, maxcardinality=False)
    by_name = {p.name: p for p in planets}
    pairs = []
    for name_a, name_b in matching:
        data = graph.edges[name_a, name_b]
        a, b = sorted((by_name[name_a], by_name[name_b]), key=lambda p: p.name)
        pairs.append(ScoredPair(a, b, int(data["weight"]), bool(data["typed"])))
    pairs.sort(key=lambda p: (-p.value, p.a.name))
    return RevenueResult(tuple(pairs))
