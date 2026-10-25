"""Per-game statistics read from a finished game's state and log, for balance analysis.

Nothing here affects play. Counts that the engine does not keep as state (dividend choices,
share purchases, idle turns) are recovered from the log text written by ``game.py``.
"""

from __future__ import annotations

import heapq
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from statistics import mean, pstdev

from bby18.game import Game, LogEntry
from bby18.hexgrid import Hex
from bby18.revenue import compute_revenue
from bby18.state import CorpStatus

_PAYS = re.compile(r"^pays \d+ .*; price (\d+)$")
_WITHHOLDS = re.compile(r"^withholds \d+; price (\d+)$")
_BUYS = re.compile(r"^buys (\S+) from (ipo|pool) for \d+$")
_STARTS = re.compile(r"^starts (\S+) at par \d+$")
_SELLS = re.compile(r"^sells (\d+) (\S+) for \d+; price \d+$")
_NO_NETWORK = "takes no network action"
_SOLD_OUT = re.compile(r"^is sold out; price \d+$")
_CHART = re.compile(r"^chart \S+ exits \S+ for (\d+)$")

NEAR_PAIR_DISTANCE = 3
"""Planet pairs this many hexes apart or fewer count as near neighbors."""
AFFORDABLE_FRONTIER = 150
"""Cost of three ordinary builds: unreached planets cheaper than this are within easy reach."""


@dataclass
class CorpMetrics:
    floated: bool = False
    par: int = 0
    """Zero when the corporation never started."""
    final_price: int = 0
    """Zero when the corporation never started."""
    treasury: int = 0
    revenue: int = 0
    """Revenue of the corporation's last operating turn."""
    planets_reached: int = 0
    operating_turns: int = 0
    pays: int = 0
    withholds: int = 0
    no_network_actions: int = 0
    charts: int = 0
    nebula_charts: int = 0
    """Charts that paid the nebula surcharge."""
    chart_spend: int = 0
    upgrades: int = 0
    services: int = 0
    top_price_turns: int = 0
    """Operating turns that ended with the price at the top of the stock market."""
    sold_out: int = 0
    """Stock rounds that ended with every share in players' hands."""
    unreached_planets: int = 0
    """Planets outside the corporation's final network (floated corporations only)."""
    next_planet_cost: int = 0
    """Cheapest build cost from the final network to any unreached planet; 0 if none is left."""
    cheap_unreached: int = 0
    """Unreached planets whose cheapest route costs under ``AFFORDABLE_FRONTIER``."""


@dataclass
class StockCounts:
    corps_started: int = 0
    ipo_buys: int = 0
    """IPO purchases after the president's share; starting a corporation is not counted."""
    pool_buys: int = 0
    shares_sold: int = 0
    sell_actions: int = 0


@dataclass
class LogCounts:
    corps: dict[str, CorpMetrics] = field(default_factory=dict)
    stock: StockCounts = field(default_factory=StockCounts)


def count_log(
    log: list[LogEntry], corp_ids: list[str], top_price: int, chart_cost: int
) -> LogCounts:
    """Tally dividend, network and stock decisions from the game log. ``chart_cost`` is the
    open-space price, so a dearer chart is known to be a nebula chart."""
    counts = LogCounts(corps={c: CorpMetrics() for c in corp_ids})
    for entry in log:
        text = entry.text
        corp = counts.corps.get(entry.actor)
        if corp is not None:
            _count_corp_entry(corp, text, top_price, chart_cost)
            continue
        _count_player_entry(counts.stock, text)
    return counts


def _count_corp_entry(corp: CorpMetrics, text: str, top_price: int, chart_cost: int) -> None:
    dividend = _PAYS.match(text) or _WITHHOLDS.match(text)
    if dividend is not None:
        corp.operating_turns += 1
        if text.startswith("pays"):
            corp.pays += 1
        else:
            corp.withholds += 1
        if int(dividend.group(1)) == top_price:
            corp.top_price_turns += 1
    elif _SOLD_OUT.match(text):
        corp.sold_out += 1
    elif text == _NO_NETWORK:
        corp.no_network_actions += 1
    elif text.startswith("chart "):
        corp.charts += 1
        charted = _CHART.match(text)
        if charted is not None:
            paid = int(charted.group(1))
            corp.chart_spend += paid
            corp.nebula_charts += int(paid > chart_cost)
    elif text.startswith("upgrade "):
        corp.upgrades += 1
    elif text.startswith("service "):
        corp.services += 1


def _count_player_entry(stock: StockCounts, text: str) -> None:
    buy = _BUYS.match(text)
    if buy is not None:
        if buy.group(2) == "pool":
            stock.pool_buys += 1
        else:
            stock.ipo_buys += 1
        return
    if _STARTS.match(text):
        stock.corps_started += 1
        return
    sell = _SELLS.match(text)
    if sell is not None:
        stock.shares_sold += int(sell.group(1))
        stock.sell_actions += 1


def corporation_metrics(game: Game) -> LogCounts:
    """Log-derived counts plus each corporation's final state."""
    counts = count_log(
        game.log, list(game.corporations), game.market.top_price(), game.config.chart_cost
    )
    for corp in game.corporations.values():
        metrics = counts.corps[corp.id]
        metrics.floated = corp.floated
        metrics.treasury = corp.treasury
        metrics.revenue = corp.last_revenue
        if corp.status is not CorpStatus.UNSTARTED:
            metrics.par = corp.par
            metrics.final_price = game.price(corp)
        if corp.floated:
            metrics.planets_reached = len(game.reachable_planets(corp))
            costs = frontier_costs(game, corp.id, game.reachable(corp))
            metrics.unreached_planets = len(costs)
            metrics.next_planet_cost = min(costs.values(), default=0)
            metrics.cheap_unreached = sum(1 for c in costs.values() if c < AFFORDABLE_FRONTIER)
    return counts


def frontier_costs(game: Game, corp_id: str, reach: frozenset[Hex]) -> dict[str, int]:
    """Cheapest cost for ``corp_id`` to build from its network to each planet outside ``reach``.

    Costs are charged per hex entered: the corporation's own service is free, a tile someone
    else charted costs the service price, open space the chart price, and nebulae their
    surcharge. Asteroid fields are impassable. Tile exits are ignored, so this is a lower bound.
    """
    board, net = game.board, game.network
    served = net.service_of(corp_id)

    def entry_cost(hex: Hex) -> int:
        if board.is_planet(hex) or hex in served:
            return 0
        return game.config.service_cost if net.is_charted(hex) else game.chart_cost(hex)

    dist: dict[Hex, int] = {h: 0 for h in reach}
    heap = [(0, h) for h in dist]
    heapq.heapify(heap)
    while heap:
        d, hex = heapq.heappop(heap)
        if d > dist[hex]:
            continue
        for _, nxt in board.neighbors(hex):
            nd = d + entry_cost(nxt)
            if nd < dist.get(nxt, nd + 1):
                dist[nxt] = nd
                heapq.heappush(heap, (nd, nxt))
    return {p.name: dist[p.hex] for p in board.planets if p.hex not in reach and p.hex in dist}


@dataclass(frozen=True)
class PlanetMetrics:
    reached_by: int
    """Floated corporations whose final network reaches the planet."""
    value: float
    """Revenue the planet earns, summed over the corporations that reach it: half of the value
    of each paired route it sits in. Over all planets this adds up to total revenue."""


def planet_metrics(game: Game) -> dict[str, PlanetMetrics]:
    """How much each planet earns at the end of the game, and how many corporations reach it."""
    reached_by: Counter[str] = Counter()
    value: defaultdict[str, float] = defaultdict(float)
    for corp in game.corporations.values():
        if not corp.floated:
            continue
        for planet in game.reachable_planets(corp):
            reached_by[planet.name] += 1
        for pair in compute_revenue(game.reachable_planets(corp), game.config).pairs:
            value[pair.a.name] += pair.value / 2
            value[pair.b.name] += pair.value / 2
    return {p.name: PlanetMetrics(reached_by[p.name], value[p.name]) for p in game.board.planets}


def near_pair_links(game: Game) -> tuple[int, int, int]:
    """Planet pairs within ``NEAR_PAIR_DISTANCE`` hexes of each other, as the crow flies.

    Returns the number of such pairs, how many have both planets in one floated corporation's
    network, and how many have at least one planet that no floated corporation reaches.
    """
    reaches = [
        {p.name for p in game.reachable_planets(c)} for c in game.corporations.values() if c.floated
    ]
    covered = set().union(*reaches) if reaches else set()
    total = linked = stranded = 0
    for a, b in combinations(game.board.planets, 2):
        if a.hex.distance(b.hex) > NEAR_PAIR_DISTANCE:
            continue
        total += 1
        linked += int(any(a.name in r and b.name in r for r in reaches))
        stranded += int(a.name not in covered or b.name not in covered)
    return total, linked, stranded


def final_revenue_split(game: Game) -> tuple[int, int]:
    """Typed-pair and basic-route revenue summed over floated corporations.

    The network does not change after the last operating turn, so this is the split of the
    final operating round's revenue.
    """
    typed = basic = 0
    for corp in game.corporations.values():
        if not corp.floated:
            continue
        for pair in game.revenue(corp).pairs:
            if pair.typed:
                typed += pair.value
            else:
                basic += pair.value
    return typed, basic


@dataclass(frozen=True)
class Coverage:
    planets_total: int
    planets_reached: int
    region_reached: dict[str, int]
    region_total: dict[str, int]


def planet_coverage(game: Game) -> Coverage:
    """Planets reached by at least one floated corporation, overall and by region."""
    reached = {
        p.name for c in game.corporations.values() if c.floated for p in game.reachable_planets(c)
    }
    region_total = Counter(p.region for p in game.board.planets)
    region_reached = Counter(game.board.planet_named(n).region for n in reached)
    return Coverage(
        planets_total=len(game.board.planets),
        planets_reached=len(reached),
        region_reached={r: region_reached.get(r, 0) for r in sorted(region_total)},
        region_total=dict(sorted(region_total.items())),
    )


def worth_spread(worth: dict[str, int]) -> tuple[float, float]:
    """Winner margin over the runner-up and the coefficient of variation, both relative to
    mean worth."""
    ranked = sorted(worth.values(), reverse=True)
    if len(ranked) < 2:
        raise ValueError("Worth spread needs at least two players")
    mean_worth = mean(ranked)
    if mean_worth <= 0:
        raise ValueError(f"Mean worth {mean_worth} is not positive")
    return (ranked[0] - ranked[1]) / mean_worth, pstdev(ranked) / mean_worth
