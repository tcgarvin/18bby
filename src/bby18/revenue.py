"""Planet-pair revenue: a maximum-weight matching over a corporation's reachable planets.

Under the experimental Death Star rules the matching may use at most one pair per fleet the
corporation owns, and a pair of the construction site with a partner planet is a contract pair
worth the current stage's contract value.
"""

from __future__ import annotations

import sys
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
    contract: bool = False
    """A Death Star contract pair: the construction site with a partner planet."""

    def __str__(self) -> str:
        kind = "contract" if self.contract else "typed" if self.typed else "basic"
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

    @property
    def contract_pairs(self) -> int:
        """How many of the pairs are Death Star contract pairs."""
        return sum(1 for p in self.pairs if p.contract)


NO_PAIR_LIMIT = sys.maxsize
"""``max_pairs`` for a matching with no cap on its number of pairs (the standard rules)."""
_DUMMY_PREFIX = "\x00dummy"
"""Names of the stand-in vertices of a capped matching; no planet name starts with NUL."""


@dataclass(frozen=True)
class EconomyKey:
    """The config values that revenue depends on; part of the memo key."""

    typed_pair_value: int
    typed_pairs: frozenset[frozenset[str]]
    regional_bonus: int
    regional_bonus_regions: frozenset[str]
    basic_route_value: int
    death_star_tag: str = ""
    contract_partner_tags: frozenset[str] = frozenset()
    contract_value: int = 0
    """What a contract pair scores now; it depends on the Death Star stage, not only the
    config."""

    @classmethod
    def of(cls, config: GameConfig, contract_value: int = 0) -> EconomyKey:
        return cls(
            typed_pair_value=config.typed_pair_value,
            typed_pairs=config.typed_pairs,
            regional_bonus=config.regional_bonus,
            regional_bonus_regions=config.regional_bonus_regions,
            basic_route_value=config.basic_route_value,
            death_star_tag=config.death_star_tag,
            contract_partner_tags=config.contract_partner_tags,
            contract_value=contract_value,
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


def is_contract_pair(a: Planet, b: Planet, economy: EconomyKey) -> bool:
    """Whether ``a`` and ``b`` are the Death Star construction site and a partner planet."""
    site = economy.death_star_tag
    if not site:
        return False
    partners = economy.contract_partner_tags
    return (site in a.tags and bool(b.tags & partners)) or (
        site in b.tags and bool(a.tags & partners)
    )


def _score_pair(a: Planet, b: Planet, economy: EconomyKey) -> tuple[int, bool, bool]:
    """Value of pairing two planets, whether it is typed, and whether it is a contract.

    A contract pair scores the contract value and never the regional bonus."""
    if is_contract_pair(a, b, economy):
        return economy.contract_value, False, True
    value, typed = pair_value(a, b, economy)
    return value, typed, False


def compute_revenue(
    planets: list[Planet],
    config: GameConfig,
    *,
    contract_value: int = 0,
    max_pairs: int = NO_PAIR_LIMIT,
) -> RevenueResult:
    """Optimal non-overlapping pairing of the given mutually reachable planets.

    ``contract_value`` is what a Death Star contract pair scores now, and ``max_pairs`` caps
    the number of pairs (one per fleet under the Death Star rules); the defaults are the
    standard rules. Results are memoized on the planet set, the economy values of ``config``,
    the contract value and the cap, so bots evaluating many candidate builds never re-run the
    matching for a set already seen. The input is put in a canonical order first, so the
    chosen matching does not depend on the order the caller listed the planets in.
    """
    if max_pairs < 0:
        raise ValueError(f"max_pairs cannot be negative, got {max_pairs}")
    canonical = tuple(sorted(planets, key=lambda p: (p.hex, p.name)))
    cap = min(max_pairs, len(canonical) // 2)
    return _cached_revenue(canonical, EconomyKey.of(config, contract_value), cap)


@lru_cache(maxsize=REVENUE_CACHE_SIZE)
def _cached_revenue(
    planets: tuple[Planet, ...], economy: EconomyKey, max_pairs: int
) -> RevenueResult:
    return _match(planets, economy, max_pairs)


def _match(planets: tuple[Planet, ...], economy: EconomyKey, max_pairs: int) -> RevenueResult:
    """The best matching of ``planets`` with at most ``max_pairs`` pairs.

    Every two planets pair for at least the basic value, so the planet graph is complete and,
    with non-negative values, the best capped matching uses exactly ``max_pairs`` pairs (when
    there are enough planets). networkx has no cardinality cap, so a capped matching adds
    ``n - 2 * max_pairs`` stand-in vertices, each joined to every planet by an edge of one
    equal weight, and asks for a maximum-cardinality matching: that is perfect, the stand-ins
    take all but ``2 * max_pairs`` planets, and the best such matching leaves the best
    ``max_pairs`` real pairs.
    """
    if max_pairs <= 0:
        return RevenueResult(())
    graph: nx.Graph[str] = nx.Graph()
    for a, b in combinations(planets, 2):
        value, typed, contract = _score_pair(a, b, economy)
        graph.add_edge(a.name, b.name, weight=value, typed=typed, contract=contract)
    if max_pairs < len(planets) // 2:
        for i in range(len(planets) - 2 * max_pairs):
            for planet in planets:
                graph.add_edge(f"{_DUMMY_PREFIX}{i}", planet.name, weight=1)
        matching = nx.max_weight_matching(graph, maxcardinality=True)
    else:
        matching = nx.max_weight_matching(graph, maxcardinality=False)
    by_name = {p.name: p for p in planets}
    pairs = []
    for name_a, name_b in matching:
        if name_a.startswith(_DUMMY_PREFIX) or name_b.startswith(_DUMMY_PREFIX):
            continue
        data = graph.edges[name_a, name_b]
        a, b = sorted((by_name[name_a], by_name[name_b]), key=lambda p: p.name)
        pairs.append(
            ScoredPair(a, b, int(data["weight"]), bool(data["typed"]), bool(data["contract"]))
        )
    pairs.sort(key=lambda p: (-p.value, p.a.name))
    return RevenueResult(tuple(pairs))


def compute_revenue_uncached(
    planets: list[Planet],
    config: GameConfig,
    *,
    contract_value: int = 0,
    max_pairs: int = NO_PAIR_LIMIT,
) -> RevenueResult:
    """The same result as ``compute_revenue`` without the memo; for tests and verification."""
    canonical = tuple(sorted(planets, key=lambda p: (p.hex, p.name)))
    cap = min(max_pairs, len(canonical) // 2)
    return _match(canonical, EconomyKey.of(config, contract_value), cap)


def clear_revenue_cache() -> None:
    _cached_revenue.cache_clear()
