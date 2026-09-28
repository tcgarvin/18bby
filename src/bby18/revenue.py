"""Planet-pair revenue: a maximum-weight matching over a corporation's reachable planets."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations

import networkx as nx

from bby18.board import Planet
from bby18.config import REVENUE_CACHE_SIZE, GameConfig


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
    floor: int = 0
    """Minimum total regardless of pairs (experimental ``homeworld_basic_income``)."""

    @property
    def pair_total(self) -> int:
        return sum(p.value for p in self.pairs)

    @property
    def total(self) -> int:
        return max(self.pair_total, self.floor)


@dataclass(frozen=True)
class EconomyKey:
    """The config values that revenue depends on; part of the memo key."""

    typed_pair_value: int
    typed_pairs: frozenset[frozenset[str]]
    regional_bonus: int
    regional_bonus_regions: frozenset[str]
    basic_route_value: int

    @classmethod
    def of(cls, config: GameConfig) -> EconomyKey:
        return cls(
            typed_pair_value=config.typed_pair_value,
            typed_pairs=config.typed_pairs,
            regional_bonus=config.regional_bonus,
            regional_bonus_regions=config.regional_bonus_regions,
            basic_route_value=config.basic_route_value,
        )


def pair_value(a: Planet, b: Planet, config: GameConfig | EconomyKey) -> tuple[int, bool]:
    """Best value of pairing two planets and whether that pairing is a typed one."""
    typed = any(frozenset({ta, tb}) in config.typed_pairs for ta in a.tags for tb in b.tags)
    if not typed:
        return config.basic_route_value, False
    value = config.typed_pair_value
    if {a.region, b.region} == set(config.regional_bonus_regions):
        value += config.regional_bonus
    return value, True


def compute_revenue(planets: list[Planet], config: GameConfig) -> RevenueResult:
    """Optimal non-overlapping pairing of the given mutually reachable planets.

    Results are memoized on the planet set and the economy values of ``config``, so bots
    evaluating many candidate builds never re-run the matching for a set already seen. The
    input is put in a canonical order first, so the chosen matching does not depend on the
    order the caller listed the planets in.
    """
    canonical = tuple(sorted(planets, key=lambda p: (p.hex, p.name)))
    return _cached_revenue(canonical, EconomyKey.of(config))


@lru_cache(maxsize=REVENUE_CACHE_SIZE)
def _cached_revenue(planets: tuple[Planet, ...], economy: EconomyKey) -> RevenueResult:
    return _match(planets, economy)


def _match(planets: tuple[Planet, ...], economy: EconomyKey) -> RevenueResult:
    graph: nx.Graph[str] = nx.Graph()
    for a, b in combinations(planets, 2):
        value, typed = pair_value(a, b, economy)
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


def compute_revenue_uncached(planets: list[Planet], config: GameConfig) -> RevenueResult:
    """The same result as ``compute_revenue`` without the memo; for tests and verification."""
    canonical = tuple(sorted(planets, key=lambda p: (p.hex, p.name)))
    return _match(canonical, EconomyKey.of(config))


def clear_revenue_cache() -> None:
    _cached_revenue.cache_clear()
