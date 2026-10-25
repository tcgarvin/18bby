"""A one-step greedy bot: builds toward revenue, buys into the best-earning corporations.

Its policies are tunable through ``GreedyPolicy`` so a sweep can check whether a balance
finding comes from the game or from one bot habit. ``GreedyPolicy()`` is the original bot.
"""

from __future__ import annotations

import heapq
import random
from dataclasses import dataclass

from bby18.actions import (
    BuyShare,
    Chart,
    ExtendService,
    NetworkAction,
    NoNetworkAction,
    PassStock,
    SellShares,
    ShareSource,
    StockAction,
    Upgrade,
)
from bby18.board import Planet
from bby18.game import Game
from bby18.hexgrid import Hex
from bby18.revenue import compute_revenue
from bby18.state import Corporation, CorpStatus, Player

START_ORDERS = ("fixed", "random", "best_home")
PAR_CHOICES = ("min", "max", "random", "mid")
ROUTING_MODES = ("straight", "path")
NO_ROUTE_COST = 1000
"""Stand-in route cost for a build that leads nowhere new; larger than any real route."""
START_SCORE = 1.0
"""Stock score of starting a corporation, above any other buy."""
FLOAT_SEEKING_SCORE = 0.9
"""Stock score of an IPO buy toward floating one's own corporation: below starting one, above
ordinary buys, and above the cash-reserve cutoff so the bot never passes instead."""


@dataclass(frozen=True)
class GreedyPolicy:
    """Knobs for ``GreedyBot``. The defaults reproduce the original greedy bot exactly.

    When ``max_presidencies > 1`` or ``par_choice != "min"``, the bot also seeks to float what
    it starts: it starts another corporation only once all its presidencies have floated, and
    ranks IPO buys in its own unfloated corporations just below starting one.
    """

    start_order: str = "fixed"
    """Which unstarted corporation to start: "fixed" (config order), "random", or
    "best_home" (highest revenue potential near its homeworld, ties random)."""
    par_choice: str = "min"
    """Par when starting: "min", "max", "random" or "mid" among the affordable pars. "max" is
    the highest par the player can float alone, or the highest affordable if none."""
    max_presidencies: int = 1
    """How many corporations this player will start."""
    pay_threshold: int = 2
    """Pay dividends when treasury >= pay_threshold * chart_cost."""
    withhold_when_revenue_below: int = 0
    """Withhold when this turn's revenue is below this (0 = never withhold for low revenue)."""
    sell_losers: bool = False
    """In stock rounds, sell one share of a held corporation priced below par that this
    player does not preside over."""
    lookahead_distance_weight: float = 10.0
    """Network score penalty per hex from a build to the nearest unreached planet."""
    cost_weight: float = 0.1
    """Network score penalty per credit of build cost."""
    home_radius: int = 3
    """How far from a homeworld "best_home" looks when valuing it."""
    routing: str = "straight"
    """How builds are ranked when they do not reach a new planet. "straight" counts hexes to the
    nearest unreached planet as the crow flies; "path" prices the cheapest route around asteroid
    fields and through nebulae, and judges a tile by where its far exit leads."""
    path_cost_weight: float = 0.2
    """With "path" routing: network score penalty per credit of remaining route cost."""

    def __post_init__(self) -> None:
        if self.start_order not in START_ORDERS:
            raise ValueError(f"start_order must be one of {START_ORDERS}, not {self.start_order!r}")
        if self.par_choice not in PAR_CHOICES:
            raise ValueError(f"par_choice must be one of {PAR_CHOICES}, not {self.par_choice!r}")
        if self.max_presidencies < 0:
            raise ValueError("max_presidencies must be non-negative")
        if self.routing not in ROUTING_MODES:
            raise ValueError(f"routing must be one of {ROUTING_MODES}, not {self.routing!r}")


class GreedyBot:
    def __init__(self, rng: random.Random, policy: GreedyPolicy = GreedyPolicy()) -> None:
        self.rng = rng
        self.policy = policy
        # The original bot (min par, one presidency) never needs help floating; any policy
        # that raises the par or allows a second start can strand parred corporations, so
        # those policies finish floating what they start before starting more.
        self.seeks_float = policy.max_presidencies > 1 or policy.par_choice != "min"

    # --- stock round ---------------------------------------------------------

    def choose_stock_action(
        self, game: Game, player: Player, legal: list[StockAction]
    ) -> StockAction:
        if self.policy.sell_losers:
            sale = self._loser_sale(game, player, legal)
            if sale is not None:
                return sale
        buys = [a for a in legal if isinstance(a, BuyShare)]
        if not buys:
            return PassStock()
        starts = self._start_options(game, player, buys)
        # Prefer buying into floated corporations by revenue per credit. Starting a corporation
        # scores START_SCORE, above any ordinary buy; the start options fill their slots in
        # policy order. Float-seeking policies also score FLOAT_SEEKING_SCORE for IPO buys that
        # help their own unfloated corporations float.
        scored: list[tuple[float, BuyShare]] = []
        start_slots = iter(starts)
        for action in buys:
            corp = game.corp(action.corp_id)
            if corp.status is CorpStatus.UNSTARTED:
                if any(s.corp_id == corp.id for s in starts) and _is_first_par(action, buys):
                    scored.append((START_SCORE, next(start_slots)))
                continue
            if self.seeks_float and self._helps_own_float(corp, player, action):
                scored.append((FLOAT_SEEKING_SCORE, action))
                continue
            cost = game.ipo_price(corp) if action.source is ShareSource.IPO else game.price(corp)
            expected = max(corp.last_revenue, 10) / game.config.shares_per_corporation
            own_bonus = 1.5 if corp.president == player.id else 1.0
            scored.append((own_bonus * expected / cost, action))
        if not scored:
            return PassStock()
        scored.sort(key=lambda t: -t[0])
        best_score = scored[0][0]
        # Keep a cash reserve unless the deal is clearly good.
        if best_score < 0.02 and player.cash < 200:
            return PassStock()
        return scored[0][1]

    @staticmethod
    def _helps_own_float(corp: Corporation, player: Player, action: BuyShare) -> bool:
        """An IPO buy in a corporation this player presides over that has not floated yet."""
        return (
            corp.status is CorpStatus.PARRED
            and corp.president == player.id
            and action.source is ShareSource.IPO
        )

    def _start_options(self, game: Game, player: Player, buys: list[BuyShare]) -> list[BuyShare]:
        """One start action per startable corporation, in the order this policy prefers."""
        presided = [c for c in game.corporations.values() if c.president == player.id]
        if len(presided) >= self.policy.max_presidencies:
            return []
        if self.seeks_float and any(not c.floated for c in presided):
            return []
        pars: dict[str, list[int]] = {}
        for action in buys:
            if game.corp(action.corp_id).status is CorpStatus.UNSTARTED:
                pars.setdefault(action.corp_id, []).append(action.par)
        options: list[BuyShare] = []
        for corp_id, affordable in pars.items():
            par = self._choose_par(game, player, sorted(affordable))
            if par is not None:
                options.append(BuyShare(corp_id, ShareSource.IPO, par))
        return self._order_starts(game, options)

    def _choose_par(self, game: Game, player: Player, affordable: list[int]) -> int | None:
        """The par to start at, or ``None`` if this policy will not start at any affordable par."""
        choice = self.policy.par_choice
        if choice == "min":
            # The original bot only ever started at the game's lowest par.
            lowest = min(game.config.par_prices)
            return lowest if lowest in affordable else None
        if choice == "max":
            # The highest par this player can float alone; a higher one strands the corporation.
            floatable = [
                p for p in affordable if p * game.config.float_threshold_shares <= player.cash
            ]
            return floatable[-1] if floatable else affordable[-1]
        if choice == "mid":
            return affordable[len(affordable) // 2]
        return self.rng.choice(affordable)

    def _order_starts(self, game: Game, options: list[BuyShare]) -> list[BuyShare]:
        order = self.policy.start_order
        if order == "fixed" or len(options) < 2:
            return options
        if order == "random":
            shuffled = list(options)
            self.rng.shuffle(shuffled)
            return shuffled
        keyed = [
            (-self.home_potential(game, game.corp(o.corp_id)), self.rng.random(), o)
            for o in options
        ]
        keyed.sort(key=lambda t: (t[0], t[1]))
        return [o for _, _, o in keyed]

    def home_potential(self, game: Game, corp: Corporation) -> int:
        """Best revenue from the planets within ``home_radius`` hexes of the homeworld.

        Pure board geometry: it ignores the network and other corporations.
        """
        home = game.homeworld(corp)
        nearby = [p for p in game.board.planets if p.hex.distance(home) <= self.policy.home_radius]
        return compute_revenue(nearby, game.config).total

    def _loser_sale(
        self, game: Game, player: Player, legal: list[StockAction]
    ) -> SellShares | None:
        """A legal one-share sale of the held non-presidency corporation furthest below par."""
        worst: tuple[float, SellShares] | None = None
        for action in legal:
            if not isinstance(action, SellShares) or action.count != 1:
                continue
            corp = game.corp(action.corp_id)
            if corp.president == player.id or game.price(corp) >= corp.par:
                continue
            ratio = game.price(corp) / corp.par
            if worst is None or ratio < worst[0]:
                worst = (ratio, action)
        return None if worst is None else worst[1]

    # --- operating round -----------------------------------------------------

    def choose_network_action(
        self, game: Game, corp: Corporation, legal: list[NetworkAction]
    ) -> NetworkAction:
        candidates = [a for a in legal if not isinstance(a, NoNetworkAction)]
        if not candidates:
            return NoNetworkAction()
        current = game.revenue(corp).total
        reach = game.reachable(corp)
        unreached = [p for p in game.board.planets if p.hex not in reach]
        to_go = self._route_costs(game, corp, unreached) if self.policy.routing == "path" else {}
        best: tuple[float, NetworkAction] | None = None
        for action in candidates:
            gain = self._revenue_after(game, corp, action, reach) - current
            if self.policy.routing == "path":
                remaining = self._remaining_route_cost(game, action, reach, to_go)
                progress_penalty = remaining * self.policy.path_cost_weight
            else:
                progress_penalty = (
                    self._straight_distance(action, unreached)
                    * self.policy.lookahead_distance_weight
                )
            score = (
                gain * 100
                - progress_penalty
                - action.cost * self.policy.cost_weight
                + self.rng.random()
            )
            if best is None or score > best[0]:
                best = (score, action)
        assert best is not None
        if best[0] < -50 and corp.treasury < game.config.chart_cost * 2:
            return NoNetworkAction()
        return best[1]

    @staticmethod
    def _straight_distance(action: NetworkAction, unreached: list[Planet]) -> int:
        """Hexes from where ``action`` builds to the nearest unreached planet, ignoring terrain."""
        if isinstance(action, (Chart, ExtendService)):
            position: Hex = action.hex
        else:
            assert isinstance(action, Upgrade)
            position = action.hex.neighbor(action.new_exit)
        return min((p.hex.distance(position) for p in unreached), default=0)

    @staticmethod
    def _route_costs(game: Game, corp: Corporation, unreached: list[Planet]) -> dict[Hex, int]:
        """Cheapest cost to build from each hex to some unreached planet, charged per hex entered.

        Open space costs the chart cost, a nebula adds its surcharge, a tile someone already
        charted costs the service cost, and the corporation's own service is free. Asteroid
        fields are not on the board's adjacency, so routes go around them.
        """
        board, net = game.board, game.network
        served = net.service_of(corp.id)

        def entry_cost(hex: Hex) -> int:
            if board.is_planet(hex) or hex in served:
                return 0
            if net.is_charted(hex):
                return game.config.service_cost
            return game.chart_cost(hex)

        dist: dict[Hex, int] = {p.hex: 0 for p in unreached}
        heap = [(0, h) for h in dist]
        heapq.heapify(heap)
        while heap:
            d, hex = heapq.heappop(heap)
            if d > dist.get(hex, d):
                continue
            for _, nxt in board.neighbors(hex):
                nd = d + entry_cost(nxt)
                if nd < dist.get(nxt, nd + 1):
                    dist[nxt] = nd
                    heapq.heappush(heap, (nd, nxt))
        return dist

    @staticmethod
    def _remaining_route_cost(
        game: Game, action: NetworkAction, reach: frozenset[Hex], to_go: dict[Hex, int]
    ) -> int:
        """Route cost still to pay beyond ``action``, judged by the hexes its far exits lead to.

        Exits that lead back into the corporation's own network make no progress, so a build
        with only such exits scores as if no route remained.
        """
        board = game.board
        if isinstance(action, Chart):
            exits = action.exits
            origin = action.hex
        elif isinstance(action, Upgrade):
            exits = frozenset({action.new_exit})
            origin = action.hex
        else:
            assert isinstance(action, ExtendService)
            tile = game.network.tile_at(action.hex)
            assert tile is not None
            exits = tile.exits
            origin = action.hex
        far = [
            origin.neighbor(d)
            for d in exits
            if origin.neighbor(d) in board.hexes and origin.neighbor(d) not in reach
        ]
        return min((to_go[h] for h in far if h in to_go), default=NO_ROUTE_COST)

    def _revenue_after(
        self, game: Game, corp: Corporation, action: NetworkAction, reach: frozenset[Hex]
    ) -> int:
        """Revenue after ``action``; ``reach`` is the corporation's current reachable set."""
        net = game.network.copy()
        if isinstance(action, Chart):
            net.chart(corp.id, action.hex, action.exits, reach)
        elif isinstance(action, Upgrade):
            net.upgrade(corp.id, action.hex, action.new_exit, reach)
        elif isinstance(action, ExtendService):
            net.extend_service(corp.id, action.hex, reach)
        reach = net.reachable(corp.id, game.homeworld(corp))
        planets = [game.board.planet_at(h) for h in reach if game.board.is_planet(h)]
        return compute_revenue(planets, game.config).total

    def choose_pay_dividends(self, game: Game, corp: Corporation, revenue: int) -> bool:
        if revenue < self.policy.withhold_when_revenue_below:
            return False
        return corp.treasury >= game.config.chart_cost * self.policy.pay_threshold


def _is_first_par(action: BuyShare, buys: list[BuyShare]) -> bool:
    """Whether ``action`` is the first listed start option for its corporation."""
    return next(b for b in buys if b.corp_id == action.corp_id) is action
