"""A one-step greedy bot: builds toward revenue, buys into the best-earning corporations.

Its policies are tunable through ``GreedyPolicy`` so a sweep can check whether a balance
finding comes from the game or from one bot habit. ``GreedyPolicy()`` is the original bot.
"""

from __future__ import annotations

import copy
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
CARELESS_BUILD_CHOICES = 3
"""A careless build is one of this many runners-up by score."""
CARELESS_DIVIDEND_FRACTION = 0.5
"""A noisy bot flips its dividend decision at this fraction of its noise rate."""
FLOAT_SEEKING_SCORE = 0.9
"""Stock score of an IPO buy toward floating one's own corporation: below starting one, above
ordinary buys, and above the cash-reserve cutoff so the bot never passes instead."""


@dataclass(frozen=True)
class GreedyPolicy:
    """Knobs for ``GreedyBot``. The defaults reproduce the original greedy bot exactly.

    When ``max_presidencies > 1``, ``par_choice != "min"`` or ``own_share_bonus < 1``, the bot
    also seeks to float what it starts: it starts another corporation only once all its
    presidencies have floated, and ranks IPO buys in its own unfloated corporations just below
    starting one.
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
    own_share_bonus: float = 1.5
    """Multiplier on the buy score of shares in corporations this player presides over."""
    cash_reserve: int = 200
    """Pass rather than make a weak buy (score below ``reserve_min_score``) while cash is below
    this."""
    reserve_min_score: float = 0.02
    """The buy score below which a buy counts as weak for ``cash_reserve``."""
    last_start_round: int = 1_000
    """Start no corporation after this round (0-based stock-round cycle)."""
    withhold_until_round: int = 0
    """Withhold every turn before this round (0-based), then follow the other dividend knobs."""
    withhold_for_builds: bool = False
    """Withhold exactly when a revenue-gaining build exists that the treasury cannot afford;
    otherwise pay. Replaces ``pay_threshold`` and ``withhold_when_revenue_below``."""
    pay_when_steps: int = 0
    """Pay whenever paying would move the price at least this many columns, before the other
    dividend knobs are consulted (0 = off)."""
    dump_rivals: bool = False
    """In stock rounds, sell one share of a corporation presided over by the richest other
    player, when that player is richer than this one."""
    noise: float = 0.0
    """Carelessness, 0 to 1: the chance that a stock decision is a random pass or buy and that
    a build is one of the next few by score instead of the best. Dividends flip at
    ``CARELESS_DIVIDEND_FRACTION`` of this rate. Starting a corporation and buying toward
    floating one's own never slip. 0 plays exactly as without the knob."""

    def __post_init__(self) -> None:
        if self.start_order not in START_ORDERS:
            raise ValueError(f"start_order must be one of {START_ORDERS}, not {self.start_order!r}")
        if self.par_choice not in PAR_CHOICES:
            raise ValueError(f"par_choice must be one of {PAR_CHOICES}, not {self.par_choice!r}")
        if self.max_presidencies < 0:
            raise ValueError("max_presidencies must be non-negative")
        if not 0 <= self.noise <= 1:
            raise ValueError("noise must be between 0 and 1")
        if self.routing not in ROUTING_MODES:
            raise ValueError(f"routing must be one of {ROUTING_MODES}, not {self.routing!r}")


class GreedyBot:
    def __init__(self, rng: random.Random, policy: GreedyPolicy = GreedyPolicy()) -> None:
        self.rng = rng
        self.policy = policy
        # The original bot (min par, one presidency) never needs help floating; any policy
        # that raises the par, allows a second start or discounts its own shares can strand
        # parred corporations, so those policies finish floating what they start first.
        self.seeks_float = (
            policy.max_presidencies > 1 or policy.par_choice != "min" or policy.own_share_bonus < 1
        )

    # --- stock round ---------------------------------------------------------

    def _slips(self, chance: float) -> bool:
        """Whether this decision is a mistake. Draws from the rng only for a noisy policy, so
        a noise-free bot's games are unchanged."""
        return self.policy.noise > 0 and self.rng.random() < chance

    def choose_stock_action(
        self, game: Game, player: Player, legal: list[StockAction]
    ) -> StockAction:
        intended = self._intended_stock_action(game, player, legal)
        # Noise is carelessness in carrying out a plan, not a different plan: a careless bot
        # that never got round to starting or floating its own corporation would have no plan
        # at all, so those buys never slip.
        if self._runs_own_corporation(game, player, intended):
            return intended
        if self._slips(self.policy.noise):
            return self._careless_stock_action(game, legal)
        return intended

    @staticmethod
    def _runs_own_corporation(game: Game, player: Player, action: StockAction) -> bool:
        """Whether ``action`` starts a corporation or buys toward floating one this player
        presides over."""
        if not isinstance(action, BuyShare):
            return False
        corp = game.corp(action.corp_id)
        return corp.status is CorpStatus.UNSTARTED or GreedyBot._helps_own_float(
            corp, player, action
        )

    def _intended_stock_action(
        self, game: Game, player: Player, legal: list[StockAction]
    ) -> StockAction:
        if self.policy.dump_rivals:
            sale = self._rival_sale(game, player, legal)
            if sale is not None:
                return sale
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
            own_bonus = self.policy.own_share_bonus if corp.president == player.id else 1.0
            scored.append((own_bonus * expected / cost, action))
        if not scored:
            return PassStock()
        scored.sort(key=lambda t: -t[0])
        best_score = scored[0][0]
        # Keep a cash reserve unless the deal is clearly good.
        if best_score < self.policy.reserve_min_score and player.cash < self.policy.cash_reserve:
            return PassStock()
        return scored[0][1]

    def _careless_stock_action(self, game: Game, legal: list[StockAction]) -> StockAction:
        """A random pass or buy in an already started corporation: a plausible slip, never a
        sale or a new start, which would change the strategy rather than its execution."""
        options: list[StockAction] = [PassStock()]
        options += [
            a
            for a in legal
            if isinstance(a, BuyShare) and game.corp(a.corp_id).status is not CorpStatus.UNSTARTED
        ]
        return self.rng.choice(options)

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
        if game.round_number > self.policy.last_start_round:
            return []
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

    @staticmethod
    def _rival_sale(game: Game, player: Player, legal: list[StockAction]) -> SellShares | None:
        """A legal one-share sale of a corporation the richest other player presides over,
        if that player is richer than this one."""
        rivals = [p for p in game.players if p.id != player.id]
        if not rivals:
            return None
        leader = max(rivals, key=game.player_worth)
        if game.player_worth(leader) <= game.player_worth(player):
            return None
        for action in legal:
            if not isinstance(action, SellShares) or action.count != 1:
                continue
            if game.corp(action.corp_id).president == leader.id:
                return action
        return None

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
        scored: list[tuple[float, NetworkAction]] = []
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
            scored.append((score, action))
        # max() keeps the first of equal scores, as the original strict-greater scan did.
        best = max(scored, key=lambda t: t[0])
        if best[0] < -50 and corp.treasury < game.config.chart_cost * 2:
            return NoNetworkAction()
        if len(scored) > 1 and self._slips(self.policy.noise):
            # A near miss: one of the next few builds by score, never an arbitrary one.
            runners_up = sorted(scored, key=lambda t: -t[0])[1 : 1 + CARELESS_BUILD_CHOICES]
            return self.rng.choice(runners_up)[1]
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
        intended = self._intended_dividend(game, corp, revenue)
        if self._slips(self.policy.noise * CARELESS_DIVIDEND_FRACTION):
            return not intended
        return intended

    def _intended_dividend(self, game: Game, corp: Corporation, revenue: int) -> bool:
        steps = self.policy.pay_when_steps
        if steps and game.payout_steps(revenue, game.price(corp)) >= steps:
            return True
        if game.round_number < self.policy.withhold_until_round:
            return False
        if self.policy.withhold_for_builds:
            return not self._needs_cash_to_build(game, corp)
        if revenue < self.policy.withhold_when_revenue_below:
            return False
        return corp.treasury >= game.config.chart_cost * self.policy.pay_threshold

    def _needs_cash_to_build(self, game: Game, corp: Corporation) -> bool:
        """Whether some build would raise revenue but costs more than the treasury holds."""
        unlimited = copy.copy(corp)
        unlimited.treasury = 10**9
        reach = game.reachable(corp)
        current = game.revenue(corp).total
        return any(
            action.cost > corp.treasury and self._revenue_after(game, corp, action, reach) > current
            for action in game.legal_network_actions(unlimited)
            if not isinstance(action, NoNetworkAction)
        )


def _is_first_par(action: BuyShare, buys: list[BuyShare]) -> bool:
    """Whether ``action`` is the first listed start option for its corporation."""
    return next(b for b in buys if b.corp_id == action.corp_id) is action
