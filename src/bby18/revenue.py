"""Planet-pair revenue: a maximum-weight matching over a corporation's reachable planets.

Under the Death Star rules the matching may use at most one pair per fleet the
corporation owns, and a pair of the construction site with a partner planet is a contract pair
worth the current stage's contract value.

Under the supply-chain rules (``chain_rules``) revenue is instead the best set of chains, at
most one per facility: a chain climbs ``commodity_order`` along typed and contract links, may
stop in the middle only at a planet holding one of the corporation's facilities, and no planet
is in two chains. Basic routes stay single pairs. See ``_best_chains``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations

import networkx as nx

from bby18.board import Planet
from bby18.config import REVENUE_CACHE_SIZE, GameConfig
from bby18.hexgrid import Hex


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
class ScoredChain:
    """One supply chain (``chain_rules``): its stops in the order the cargo travels, the links
    between consecutive stops, and the regional bonus it earns once. A basic route is a chain of
    two stops and one link."""

    stops: tuple[Planet, ...]
    links: tuple[ScoredPair, ...]
    regional: int = 0

    @property
    def value(self) -> int:
        return sum(link.value for link in self.links) + self.regional

    def __str__(self) -> str:
        path = " -> ".join(stop.name for stop in self.stops)
        bonus = f" + regional {self.regional}" if self.regional else ""
        return f"{path} ({' + '.join(str(link.value) for link in self.links)}{bonus})"


@dataclass(frozen=True)
class RevenueResult:
    pairs: tuple[ScoredPair, ...]
    """Every scoring pair; under ``chain_rules``, every link of every chain."""
    floor: int = 0
    """Minimum total regardless of pairs (experimental ``homeworld_basic_income``)."""
    chains: tuple[ScoredChain, ...] = ()
    """The chains run under ``chain_rules``, best first; empty under the pair rules, where
    each pair stands alone."""

    @property
    def pair_total(self) -> int:
        return sum(p.value for p in self.pairs) + sum(c.regional for c in self.chains)

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
    planet_pair_bonus: frozenset[tuple[str, int]] = frozenset()
    """``GameConfig.planet_pair_bonus`` as hashable (planet name, bonus) items."""
    death_star_tag: str = ""
    contract_partner_tags: frozenset[str] = frozenset()
    contract_value: int = 0
    """What a contract pair scores now; it depends on the Death Star stage, not only the
    config."""
    chain_rules: bool = False
    commodity_order: frozenset[tuple[str, int]] = frozenset()
    """``GameConfig.commodity_order`` as hashable (tag, rank) items."""

    @classmethod
    def of(cls, config: GameConfig, contract_value: int = 0) -> EconomyKey:
        return cls(
            typed_pair_value=config.typed_pair_value,
            typed_pairs=config.typed_pairs,
            regional_bonus=config.regional_bonus,
            regional_bonus_regions=config.regional_bonus_regions,
            basic_route_value=config.basic_route_value,
            planet_pair_bonus=frozenset(config.planet_pair_bonus.items()),
            death_star_tag=config.death_star_tag,
            contract_partner_tags=config.contract_partner_tags,
            contract_value=contract_value,
            chain_rules=config.chain_rules,
            commodity_order=frozenset(config.commodity_order.items()),
        )


def pair_value(a: Planet, b: Planet, config: GameConfig | EconomyKey) -> tuple[int, bool]:
    """Best value of pairing two planets and whether that pairing is a typed one."""
    economy = config if isinstance(config, EconomyKey) else EconomyKey.of(config)
    bonus = sum(extra for name, extra in economy.planet_pair_bonus if name in (a.name, b.name))
    typed = any(frozenset({ta, tb}) in economy.typed_pairs for ta in a.tags for tb in b.tags)
    if not typed:
        return economy.basic_route_value + bonus, False
    value = economy.typed_pair_value + bonus
    if {a.region, b.region} == set(economy.regional_bonus_regions):
        value += economy.regional_bonus
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
    middle_stops: frozenset[Hex] = frozenset(),
) -> RevenueResult:
    """Optimal non-overlapping pairing of the given mutually reachable planets.

    ``contract_value`` is what a Death Star contract pair scores now, and ``max_pairs`` caps
    the number of pairs (one per fleet under the Death Star rules); the defaults are the
    standard rules. Under ``chain_rules`` the cap counts chains instead, and ``middle_stops``
    are the planets where a chain may stop in the middle (those holding one of the
    corporation's facilities); the pair rules ignore it. Results are memoized on the planet
    set, the economy values of ``config``, the contract value, the cap and the middle stops, so
    bots evaluating many candidate builds never re-run the search for a set already seen. The
    input is put in a canonical order first, so the result does not depend on the order the
    caller listed the planets in.
    """
    if max_pairs < 0:
        raise ValueError(f"max_pairs cannot be negative, got {max_pairs}")
    canonical = tuple(sorted(planets, key=lambda p: (p.hex, p.name)))
    cap = min(max_pairs, len(canonical) // 2)
    economy = EconomyKey.of(config, contract_value)
    middles = _relevant_middles(canonical, economy, middle_stops)
    return _cached_revenue(canonical, economy, cap, middles)


def _relevant_middles(
    planets: tuple[Planet, ...], economy: EconomyKey, middle_stops: frozenset[Hex]
) -> frozenset[Hex]:
    """The middle stops that can matter: none under the pair rules, else those among
    ``planets``. Narrowing them keeps the memo key small."""
    if not economy.chain_rules:
        return frozenset()
    return frozenset(p.hex for p in planets if p.hex in middle_stops)


@lru_cache(maxsize=REVENUE_CACHE_SIZE)
def _cached_revenue(
    planets: tuple[Planet, ...], economy: EconomyKey, max_pairs: int, middles: frozenset[Hex]
) -> RevenueResult:
    if economy.chain_rules:
        return _best_chains(planets, economy, max_pairs, middles)
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
    middle_stops: frozenset[Hex] = frozenset(),
) -> RevenueResult:
    """The same result as ``compute_revenue`` without the memo; for tests and verification."""
    canonical = tuple(sorted(planets, key=lambda p: (p.hex, p.name)))
    cap = min(max_pairs, len(canonical) // 2)
    economy = EconomyKey.of(config, contract_value)
    if economy.chain_rules:
        middles = _relevant_middles(canonical, economy, middle_stops)
        return _best_chains(canonical, economy, cap, middles)
    return _match(canonical, economy, cap)


def clear_revenue_cache() -> None:
    _cached_revenue.cache_clear()


# --- supply chains (chain_rules) ----------------------------------------------------------


@dataclass(frozen=True)
class _Candidate:
    """A typed or contract chain the search may run: its stops (indices into the canonical
    planets, in travel order), their bit mask, and its scored form."""

    stops: tuple[int, ...]
    mask: int
    chain: ScoredChain


def _best_chains(
    planets: tuple[Planet, ...], economy: EconomyKey, max_chains: int, middles: frozenset[Hex]
) -> RevenueResult:
    """The best set of at most ``max_chains`` planet-disjoint chains.

    Every typed or contract chain is enumerated (they are few: only ``middles`` may be middle
    stops and a chain only climbs), then a depth-first branch and bound picks a disjoint set,
    best candidates first. Basic routes fill the chains left over: every two planets not yet
    used pair for at least the basic value, so the best filler of ``k`` routes takes the ``2k``
    unused planets with the largest pair bonuses, in any pairing (``_basic_filler``). Search
    order and strict improvement make ties go to the earliest set in canonical order.
    """
    if max_chains <= 0 or len(planets) < 2:
        return RevenueResult(())
    candidates = _chain_candidates(planets, economy, middles)
    bonus = {name: extra for name, extra in economy.planet_pair_bonus}
    full = (1 << len(planets)) - 1
    best_value = -1
    best_set: tuple[int, ...] = ()

    def filler_value(used: int, count: int) -> int:
        return sum(
            economy.basic_route_value + b for b in _filler_bonuses(planets, bonus, used, count)
        )

    def search(start: int, used: int, chosen: tuple[int, ...], value: int) -> None:
        nonlocal best_value, best_set
        left = max_chains - len(chosen)
        total = value + filler_value(used, left)
        if total > best_value:
            best_value, best_set = total, chosen
        if left == 0:
            return
        free = bin(full & ~used).count("1")
        room = min(left, free // 2)
        top_basic = economy.basic_route_value + sum(sorted(bonus.values(), reverse=True)[:2])
        for i in range(start, len(candidates)):
            candidate = candidates[i]
            ceiling = value + room * max(candidate.chain.value, top_basic)
            if ceiling <= best_value:
                return
            if candidate.mask & used:
                continue
            search(i + 1, used | candidate.mask, chosen + (i,), value + candidate.chain.value)

    search(0, 0, (), 0)
    chains = [candidates[i].chain for i in best_set]
    used = 0
    for i in best_set:
        used |= candidates[i].mask
    chains.extend(_basic_filler(planets, economy, bonus, used, max_chains - len(best_set)))
    chains.sort(key=lambda c: (-c.value, [s.name for s in c.stops]))
    pairs = tuple(link for chain in chains for link in chain.links)
    return RevenueResult(pairs, chains=tuple(chains))


def _filler_planets(
    planets: tuple[Planet, ...], bonus: dict[str, int], used: int, count: int
) -> list[int]:
    """Indices of the unused planets the basic filler of ``count`` routes takes: the ``2k``
    with the largest pair bonuses (canonical order on ties), for ``k`` as many routes as the
    unused planets allow."""
    free = [i for i in range(len(planets)) if not used >> i & 1]
    routes = min(count, len(free) // 2)
    free.sort(key=lambda i: -bonus.get(planets[i].name, 0))
    return free[: 2 * routes]


def _filler_bonuses(
    planets: tuple[Planet, ...], bonus: dict[str, int], used: int, count: int
) -> list[int]:
    """Pair bonus of each basic filler route (see ``_filler_planets``)."""
    taken = _filler_planets(planets, bonus, used, count)
    return [
        bonus.get(planets[a].name, 0) + bonus.get(planets[b].name, 0)
        for a, b in zip(taken[::2], taken[1::2])
    ]


def _basic_filler(
    planets: tuple[Planet, ...],
    economy: EconomyKey,
    bonus: dict[str, int],
    used: int,
    count: int,
) -> list[ScoredChain]:
    """The basic routes of ``_filler_planets``, paired in order. At the optimum none of them
    is typed: a typed pair there would have made a better chain set."""
    taken = _filler_planets(planets, bonus, used, count)
    routes = []
    for a, b in zip(taken[::2], taken[1::2]):
        first, second = sorted((planets[a], planets[b]), key=lambda p: p.name)
        value, typed, contract = _score_pair(first, second, economy)
        if typed or contract:
            raise AssertionError(f"Basic filler paired {first.name} and {second.name}")
        link = ScoredPair(first, second, value, False)
        routes.append(ScoredChain((first, second), (link,)))
    return routes


def _chain_candidates(
    planets: tuple[Planet, ...], economy: EconomyKey, middles: frozenset[Hex]
) -> list[_Candidate]:
    """Every typed or contract chain over ``planets``, best first, one per sequence of stops
    (the best way of reading its tags)."""
    rank = dict(economy.commodity_order)
    links = _chain_links(planets, economy, rank)
    best: dict[tuple[int, ...], ScoredChain] = {}

    def extend(stops: tuple[int, ...], tag: str, scored: tuple[ScoredPair, ...]) -> None:
        last = stops[-1]
        for target, target_tag, link in links.get((last, tag), ()):
            path = stops + (target,)
            chain_links = scored + (link,)
            chain = ScoredChain(
                tuple(planets[i] for i in path),
                chain_links,
                _regional(tuple(planets[i] for i in path), economy),
            )
            known = best.get(path)
            if known is None or chain.value > known.value:
                best[path] = chain
            if planets[target].hex in middles:
                extend(path, target_tag, chain_links)

    for index, planet in enumerate(planets):
        for tag in sorted(planet.tags & rank.keys()):
            extend((index,), tag, ())
    candidates = []
    for path, chain in best.items():
        mask = 0
        for i in path:
            mask |= 1 << i
        candidates.append(_Candidate(path, mask, chain))
    candidates.sort(key=lambda c: (-c.chain.value, c.stops))
    return candidates


def _chain_links(
    planets: tuple[Planet, ...], economy: EconomyKey, rank: dict[str, int]
) -> dict[tuple[int, str], list[tuple[int, str, ScoredPair]]]:
    """For each (planet index, tag it plays), the links a chain may take onward: the target's
    index, the tag it plays, and the scored link. A link climbs ``rank`` and is a typed pair or
    a contract (a partner tag into the site)."""
    site = economy.death_star_tag
    links: dict[tuple[int, str], list[tuple[int, str, ScoredPair]]] = {}
    for i, source in enumerate(planets):
        for j, target in enumerate(planets):
            if i == j:
                continue
            for source_tag in sorted(source.tags & rank.keys()):
                for target_tag in sorted(target.tags & rank.keys()):
                    if rank[source_tag] >= rank[target_tag]:
                        continue
                    link = _link(source, source_tag, target, target_tag, economy, site)
                    if link is not None:
                        links.setdefault((i, source_tag), []).append((j, target_tag, link))
    return links


def _link(
    source: Planet,
    source_tag: str,
    target: Planet,
    target_tag: str,
    economy: EconomyKey,
    site: str,
) -> ScoredPair | None:
    """The scored link from ``source`` playing ``source_tag`` to ``target`` playing
    ``target_tag``, or ``None`` when that is neither a typed pair nor a contract. A link never
    carries the regional bonus: the chain earns it once."""
    if site and target_tag == site and source_tag in economy.contract_partner_tags:
        return ScoredPair(source, target, economy.contract_value, False, True)
    if frozenset({source_tag, target_tag}) not in economy.typed_pairs:
        return None
    names = (source.name, target.name)
    bonus = sum(extra for name, extra in economy.planet_pair_bonus if name in names)
    return ScoredPair(source, target, economy.typed_pair_value + bonus, True)


def _regional(stops: tuple[Planet, ...], economy: EconomyKey) -> int:
    """The regional bonus a chain with these stops earns: once, when its first stop and its
    last stop short of the construction site lie one in each regional-bonus region."""
    ends = [stop for stop in stops if economy.death_star_tag not in stop.tags]
    if len(ends) < 2:
        return 0
    if {ends[0].region, ends[-1].region} == set(economy.regional_bonus_regions):
        return economy.regional_bonus
    return 0
