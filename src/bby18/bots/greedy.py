"""A one-step greedy bot: builds toward revenue, buys into the best-earning corporations.

Its policies are tunable through ``GreedyPolicy`` so a sweep can check whether a balance
finding comes from the game or from one bot habit. ``GreedyPolicy()`` is the original bot.
"""

from __future__ import annotations

import copy
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from bby18.actions import (
    BuildFacility,
    BuyFleet,
    BuyShare,
    Chart,
    ExtendService,
    FinishFleets,
    FleetAction,
    NetworkAction,
    NoNetworkAction,
    PassStock,
    SellShares,
    ShareSource,
    StockAction,
    Upgrade,
)
from bby18.board import Planet
from bby18.bots.forecast import TrackForecast, is_fragile, next_fleet_prices
from bby18.bots.routing import PlanetDoors, RouteMap, route_costs
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
RESERVED_SITE_LEAD_TURNS = 3
"""Death Star rules: the reserved next site becomes a build target once the site is expected to
move within this many operating rounds."""


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
    """Pay dividends when treasury >= pay_threshold * chart_cost. Under the Death Star rules the
    cushion is counted beyond the fleet reserve, and a corporation below it still pays when
    nothing needs the cash soon (see ``GreedyBot._intended_death_star_dividend``)."""
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
    otherwise pay. Replaces ``pay_threshold`` and ``withhold_when_revenue_below``. Under the
    Death Star rules a wanted fleet it cannot pay for also counts, and a build is affordable
    only from what the fleet reserve leaves."""
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

    # The knobs below matter only under the Death Star rules. Under the facility
    # rules the fleet knobs apply to facilities (see ``GreedyBot._choose_facility``).
    fleet_payback_turns: float = 4.0
    """Buy a fleet when the revenue it adds, over at most this many operating turns (and no more
    than the turns the game is expected to last), covers its price. A facility also counts
    what its exit saves on the way to the next target."""
    fleet_target: int = 0
    """0: buy fleets by value (``fleet_payback_turns``). N > 0: own exactly N, buying whenever
    affordable regardless of value, and no more. Under the facility rules N counts the free
    home facility."""
    contract_weight: float = 1.0
    """How much a build values the Death Star site: its contract value is scaled by this when
    planning builds and routes. 0 never builds toward or routes through the site (it still
    scores a contract if its network happens to reach it); 2 rushes it."""
    treasury_reserve_fleets: float = 0.0
    """Keep this many fleet prices in the treasury: never spend them on builds and withhold
    until they are there. Fleets themselves may be bought from it."""
    sell_own_before_seizure: bool = False
    """In a stock round before a likely seizure, sell shares of corporations this player
    presides over down to what keeps the presidency."""

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
        if self.fleet_payback_turns <= 0:
            raise ValueError("fleet_payback_turns must be positive")
        if self.fleet_target < 0:
            raise ValueError("fleet_target must be non-negative")
        if self.contract_weight < 0:
            raise ValueError("contract_weight must be non-negative")
        if self.treasury_reserve_fleets < 0:
            raise ValueError("treasury_reserve_fleets must be non-negative")


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
        death_star = game.config.death_star_rules
        fragile: frozenset[str] = frozenset()
        if death_star:
            forecast = TrackForecast.of(game)
            fragile = self._fragile_corporations(game, forecast)
            if self.policy.sell_own_before_seizure:
                sale = self._own_sale_before_seizure(game, player, legal, forecast)
                if sale is not None:
                    return sale
        if self.policy.dump_rivals:
            sale = self._rival_sale(game, player, legal)
            if sale is not None:
                return sale
        if self.policy.sell_losers:
            if death_star:
                sale = self._fragile_sale(game, player, legal, fragile)
                if sale is not None:
                    return sale
            sale = self._loser_sale(game, player, legal)
            if sale is not None:
                return sale
        buys = [a for a in legal if isinstance(a, BuyShare)]
        if death_star:
            # A corporation that may close this round would take its shares with it.
            buys = [a for a in buys if a.corp_id not in fragile]
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
        return game.planet_revenue(nearby).total

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
    def _fragile_corporations(game: Game, forecast: TrackForecast) -> frozenset[str]:
        """Floated corporations that may close in the coming round (Death Star rules)."""
        return frozenset(
            c.id
            for c in game.corporations.values()
            if c.status is CorpStatus.FLOATED and is_fragile(game, c.id, forecast)
        )

    @staticmethod
    def _fragile_sale(
        game: Game, player: Player, legal: list[StockAction], fragile: frozenset[str]
    ) -> SellShares | None:
        """The largest legal sale of a ``fragile`` corporation this player does not preside
        over."""
        sales = [
            a
            for a in legal
            if isinstance(a, SellShares)
            and a.corp_id in fragile
            and game.corp(a.corp_id).president != player.id
        ]
        return max(sales, key=lambda a: a.count, default=None)

    @staticmethod
    def _own_sale_before_seizure(
        game: Game, player: Player, legal: list[StockAction], forecast: TrackForecast
    ) -> SellShares | None:
        """Before a likely seizure, the largest legal sale of a corporation this player presides
        over that still leaves it the presidency."""
        if not forecast.seizure_within_round:
            return None
        best: SellShares | None = None
        for action in legal:
            if not isinstance(action, SellShares):
                continue
            corp = game.corp(action.corp_id)
            if corp.president != player.id:
                continue
            rivals = max(
                (p.shares_in(corp.id) for p in game.players if p.id != player.id), default=0
            )
            keep = max(game.config.president_share_size, rivals)
            if player.shares_in(corp.id) - action.count < keep:
                continue
            if best is None or action.count > best.count:
                best = action
        return best

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
        death_star = game.config.death_star_rules
        if death_star:
            forecast = TrackForecast.of(game)
            # Never spend what the fleets the corporation needs to survive will cost.
            budget = corp.treasury - self._build_reserve(game, forecast, corp)
            candidates = [a for a in candidates if a.cost <= budget]
        if not candidates:
            return NoNetworkAction()
        reach = game.reachable(corp)
        gains: Sequence[float]
        if death_star:
            revenue_gains = self._death_star_gains(game, forecast, corp, candidates, reach)
            # A build that costs revenue (by taking the money for a fleet) is never worth it.
            kept = [(a, g) for a, g in zip(candidates, revenue_gains) if g >= 0]
            if not kept:
                return NoNetworkAction()
            candidates = [a for a, _ in kept]
            targets = self._death_star_targets(game, forecast, reach)
            blocked = self._blocked_hexes(game)
            rush = self._rush_bonuses(game, forecast, corp, candidates, reach, blocked)
            gains = [g + r for (_, g), r in zip(kept, rush)]
        else:
            current = game.revenue(corp).total
            gains = [self._revenue_after(game, corp, a, reach) - current for a in candidates]
            targets = {p.hex: 1.0 for p in game.board.planets if p.hex not in reach}
            blocked = frozenset()
        to_go = (
            self._weighted_route_costs(game, corp, targets, blocked)
            if self.policy.routing == "path"
            else None
        )
        scored: list[tuple[float, NetworkAction]] = []
        for action, gain in zip(candidates, gains):
            if to_go is not None:
                remaining = self._remaining_route_cost(game, action, reach, to_go)
                progress_penalty = remaining * self.policy.path_cost_weight
            else:
                progress_penalty = (
                    self._straight_distance(action, targets) * self.policy.lookahead_distance_weight
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
    def _straight_distance(action: NetworkAction, targets: dict[Hex, float]) -> float:
        """Hexes from where ``action`` builds to the nearest target, ignoring terrain. Targets
        map to weights (1 for a planet); a target of weight w counts as 1/w as far."""
        if isinstance(action, (Chart, ExtendService)):
            position: Hex = action.hex
        else:
            assert isinstance(action, Upgrade)
            position = action.hex.neighbor(action.new_exit)
        return min(
            (_weighted(h.distance(position), weight) for h, weight in targets.items()), default=0
        )

    @staticmethod
    def _weighted_route_costs(
        game: Game, corp: Corporation, targets: dict[Hex, float], blocked: frozenset[Hex]
    ) -> RouteMap:
        """``_route_costs`` to the nearest target, where targets map to weights (1 for a
        planet) and a route to a target of weight w costs 1/w as much."""
        by_weight: dict[float, list[Hex]] = {}
        for hex, weight in targets.items():
            by_weight.setdefault(weight, []).append(hex)
        combined: dict[Hex, float] = {}
        for weight, hexes in by_weight.items():
            for hex, cost in GreedyBot._route_costs(game, corp, hexes, blocked).items():
                scaled = _weighted(cost, weight)
                if hex not in combined or scaled < combined[hex]:
                    combined[hex] = scaled
        return GreedyBot._route_map(game, corp, combined, targets, blocked)

    @staticmethod
    def _route_map(
        game: Game,
        corp: Corporation,
        costs: dict[Hex, float],
        targets: dict[Hex, float],
        blocked: frozenset[Hex],
    ) -> RouteMap:
        """``costs`` from ``_route_costs`` to ``targets`` (hex -> weight), as a ``RouteMap``
        that can also price steps into exit-limited planets."""
        return RouteMap(
            costs,
            game.board,
            targets,
            blocked,
            frozenset(game.death_star_reserved_sites()),
            PlanetDoors.of(game, corp),
        )

    @staticmethod
    def _route_costs(
        game: Game, corp: Corporation, targets: list[Hex], blocked: frozenset[Hex]
    ) -> dict[Hex, int]:
        """Cheapest cost to build from each hex to some target, charged per hex entered, with
        the planet exits ``corp`` faces under the facility rules (see ``bby18.bots.routing``).
        """
        return route_costs(
            game, game.network, corp.id, targets, blocked, PlanetDoors.of(game, corp)
        )

    @staticmethod
    def _remaining_route_cost(
        game: Game, action: NetworkAction, reach: frozenset[Hex], to_go: RouteMap
    ) -> float:
        """Route cost still to pay beyond ``action``, judged by the hexes its far exits lead to.

        Exits that lead back into the corporation's own network make no progress, so a build
        with only such exits scores as if no route remained. A far exit facing an exit-limited
        planet pays for the planet's exits too (``RouteMap.beyond``): a lane toward a planet
        with no exit left is worth building only as the first step of buying one there.
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
        costs = (to_go.beyond(origin, h) for h in far)
        return min((c for c in costs if c is not None), default=NO_ROUTE_COST)

    @staticmethod
    def _planets_after(
        game: Game, corp: Corporation, action: NetworkAction, reach: frozenset[Hex]
    ) -> list[Planet]:
        """The planets ``corp`` would reach after ``action``; ``reach`` is its reachable set
        now."""
        net = game.network.copy()
        if isinstance(action, Chart):
            net.chart(corp.id, action.hex, action.exits, reach)
        elif isinstance(action, Upgrade):
            net.upgrade(corp.id, action.hex, action.new_exit, reach)
        elif isinstance(action, ExtendService):
            net.extend_service(corp.id, action.hex, reach)
        after = net.reachable(corp.id, game.homeworld(corp))
        return [game.board.planet_at(h) for h in after if game.board.is_planet(h)]

    def _revenue_after(
        self, game: Game, corp: Corporation, action: NetworkAction, reach: frozenset[Hex]
    ) -> int:
        """Revenue after ``action`` under the standard rules, with no pair cap."""
        planets = self._planets_after(game, corp, action, reach)
        return game.planet_revenue(planets).total

    def choose_fleet_action(
        self, game: Game, corp: Corporation, legal: list[FleetAction]
    ) -> FleetAction:
        """Buy the mandatory first fleet, then fleets by ``fleet_target`` or by value (see
        ``_wants_fleet``). Under the facility rules, build facilities instead (see
        ``_choose_facility``)."""
        if game.config.facility_rules:
            builds = [a for a in legal if isinstance(a, BuildFacility)]
            return self._choose_facility(game, corp, builds) if builds else FinishFleets()
        buys = [a for a in legal if isinstance(a, BuyFleet)]
        if not buys:
            return FinishFleets()
        wanted = self._wants_fleet(
            game,
            TrackForecast.of(game),
            corp.fleets,
            game.reachable_planets(corp),
            game.contract_value(),
            buys[0].cost,
        )
        return buys[0] if wanted else FinishFleets()

    def _choose_facility(
        self, game: Game, corp: Corporation, builds: Sequence[BuildFacility]
    ) -> FleetAction:
        """The facility to build next, or finishing the step (facility rules).

        A facility is a fleet with an address: it adds a pair, and it gives its planet an exit.
        Each build is valued at what the pair (and any planets the new exit connects) adds over
        the payback horizon, as ``_wants_fleet`` values a fleet, plus how much cheaper it makes
        the cheapest route from the network to a build target (``_FacilityOption``), counted
        in full only while there are turns left to build along it (``_route_share``). The first
        facility is mandatory and a ``fleet_target`` policy builds up to its target whatever
        the value; otherwise a build is made when its value covers the price, or when it is the
        second facility, earns something and a seizure would otherwise call for a replacement.
        The build made is the most valuable, then the one whose exit goes to the builder's own
        dangling lane rather than left unclaimed, and unclaimed rather than given to a lane only
        rivals serve; then the one whose exit opens the cheapest route out of the network that
        the planet did not already offer (``_FacilityOption.opening``), so that a facility built
        for its pair alone still puts its exit where the next lane can use it; then the one
        farthest from the construction site (the Empire takes the nearest), then the first
        listed.
        """
        choice = self._facility_choice(game, TrackForecast.of(game), corp, builds)
        return FinishFleets() if choice is None else choice

    def _facility_choice(
        self,
        game: Game,
        forecast: TrackForecast,
        corp: Corporation,
        builds: Sequence[BuildFacility],
    ) -> BuildFacility | None:
        """The build ``_choose_facility`` makes from ``builds``, or ``None`` to finish."""
        owned = corp.fleets
        target = self.policy.fleet_target
        if not builds or (owned > 0 and target > 0 and owned >= target):
            return None
        options = self._facility_options(game, forecast, corp, builds)
        horizon = min(forecast.turns_left, self.policy.fleet_payback_turns)
        route_share = self._route_share(forecast)

        def value(option: _FacilityOption) -> float:
            return option.marginal * horizon + option.route_saving * route_share

        if owned == 0 or target > 0:
            eligible = options
        else:
            price = builds[0].cost
            insure = owned == 1 and forecast.fleet_reserve(1, options[0].revenue_now) > 0
            eligible = [o for o in options if value(o) >= price or (insure and o.marginal > 0)]
        if not eligible:
            return None

        def key(indexed: tuple[int, _FacilityOption]) -> tuple[float, int, float, int, int]:
            index, option = indexed
            return value(option), -option.gift, -option.opening, option.site_distance, -index

        return max(enumerate(eligible), key=key)[1].action

    def _route_share(self, forecast: TrackForecast) -> float:
        """How much of a facility's route saving counts: all of it with ``fleet_payback_turns``
        turns left after this one to build along the route and earn from where it leads, less
        with fewer, none in the last turn."""
        return max(0.0, min(1.0, (forecast.turns_left - 1) / self.policy.fleet_payback_turns))

    def _facility_options(
        self,
        game: Game,
        forecast: TrackForecast,
        corp: Corporation,
        builds: Sequence[BuildFacility],
    ) -> list[_FacilityOption]:
        """``builds`` as the facility step values them (see ``_FacilityOption``).

        Revenue is the planning view (the site's contracts weighted by ``_site_weight``). Route
        savings are measured toward the targets network actions aim at
        (``_death_star_targets``), less any planet the build itself connects, whose revenue
        already counts: the cheapest route from the network now, against the cheapest from the
        network after the build, through the planet's new exit, priced beyond the network as
        now (``RouteMap.with_doors``)."""
        board = game.board
        weight = self._site_weight(game, forecast)
        planets, contract_value = self._planning_view(game, weight, game.reachable_planets(corp))
        owned = corp.fleets
        revenue_now = self._capped_revenue(game, planets, owned, contract_value)
        reach = game.reachable(corp)
        home = game.homeworld(corp)
        site = game.death_star_site()
        targets = self._death_star_targets(game, forecast, reach)
        blocked = self._blocked_hexes(game)
        doors = PlanetDoors.of(game, corp)
        assert doors is not None
        next_price = next_fleet_prices(game, 2)[1]
        can_build_more = owned + 1 < game.config.fleet_limit
        routes: dict[frozenset[Hex], tuple[RouteMap, float]] = {}
        options = []
        for action in builds:
            net = game.network_after_facility(action)
            after = net.reachable(corp.id, home)
            connected = frozenset(h for h in after - reach if board.is_planet(h))
            if connected not in routes:
                aims = {h: w for h, w in targets.items() if h not in connected}
                to_go = self._weighted_route_costs(game, corp, aims, blocked)
                before = to_go.from_network(reach)
                routes[connected] = (to_go, NO_ROUTE_COST if before is None else before)
            to_go, route_before = routes[connected]
            slots = dict(doors.slots)
            slots[action.planet] -= 1
            doors_after = replace(
                doors,
                network=net,
                facility_price=next_price,
                can_build=can_build_more,
                slots=slots,
            )
            map_after = to_go.with_doors(doors_after)
            route_after = map_after.from_network(after)
            saving = route_before - (NO_ROUTE_COST if route_after is None else route_after)
            opening = self._exit_opening(
                action.planet, reach, after, to_go.from_hex, map_after.from_hex
            )
            after_planets, _ = self._planning_view(
                game, weight, [board.planet_at(h) for h in sorted(after) if board.is_planet(h)]
            )
            revenue = self._capped_revenue(game, after_planets, owned + 1, contract_value)
            options.append(
                _FacilityOption(
                    action=action,
                    revenue_now=revenue_now,
                    marginal=revenue - revenue_now,
                    route_saving=max(0.0, saving),
                    opening=opening,
                    gift=self._exit_gift(game, corp, action),
                    site_distance=action.planet.distance(site) if site is not None else 0,
                )
            )
        return options

    @staticmethod
    def _exit_opening(
        planet: Hex,
        reach: frozenset[Hex],
        after: frozenset[Hex],
        route_before: Callable[[Hex, frozenset[Hex]], float | None],
        route_after: Callable[[Hex, frozenset[Hex]], float | None],
    ) -> float:
        """The cheapest route out of the network from ``planet`` after the build, if the build
        made it cheaper than it was (the new exit opens a way the planet did not offer); else
        ``NO_ROUTE_COST``, as for a planet the network does not reach."""
        if planet not in after:
            return NO_ROUTE_COST
        now = route_after(planet, after)
        if now is None:
            return NO_ROUTE_COST
        was = route_before(planet, reach) if planet in reach else None
        if was is not None and was <= now:
            return NO_ROUTE_COST
        return now

    @staticmethod
    def _exit_gift(game: Game, corp: Corporation, action: BuildFacility) -> int:
        """Whom ``action``'s new exit serves: 0 a dangling lane on a tile ``corp`` serves, 1
        nobody yet (left unclaimed, for the next tile charted toward the planet), 2 a lane
        only rivals serve."""
        if action.exit_side is None:
            return 1
        lane = action.planet.neighbor(action.exit_side)
        return 0 if corp.id in game.network.corporations_serving(lane) else 2

    def choose_pay_dividends(self, game: Game, corp: Corporation, revenue: int) -> bool:
        intended = self._intended_dividend(game, corp, revenue)
        if self._slips(self.policy.noise * CARELESS_DIVIDEND_FRACTION):
            return not intended
        return intended

    def _intended_dividend(self, game: Game, corp: Corporation, revenue: int) -> bool:
        if game.config.death_star_rules:
            return self._intended_death_star_dividend(game, corp, revenue)
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

    # --- Death Star rules ------------------------------------------------------

    def _wants_fleet(
        self,
        game: Game,
        forecast: TrackForecast,
        owned: int,
        planets: list[Planet],
        contract_value: int,
        price: int,
    ) -> bool:
        """Whether a corporation owning ``owned`` fleets, reaching ``planets``, would buy one
        more at ``price`` (assuming it can pay and is under the limit).

        The first fleet is mandatory. A ``fleet_target`` policy buys up to its target and stops.
        Otherwise it buys when the pair the fleet adds pays back its price within
        ``fleet_payback_turns`` (and the turns the game is expected to last), or when it owns
        one, the second would earn something, and it must otherwise keep a replacement's price
        against a seizure: a second fleet protects it as well as the money would.
        """
        if owned == 0:
            return True
        target = self.policy.fleet_target
        if target > 0:
            return owned < target
        now = self._capped_revenue(game, planets, owned, contract_value)
        marginal = self._capped_revenue(game, planets, owned + 1, contract_value) - now
        if owned == 1 and marginal > 0 and forecast.fleet_reserve(1, now) > 0:
            return True
        return marginal * min(forecast.turns_left, self.policy.fleet_payback_turns) >= price

    def _fleets_to_buy(
        self,
        game: Game,
        forecast: TrackForecast,
        corp: Corporation,
        treasury: int,
        planets: list[Planet],
        contract_value: int,
    ) -> int:
        """How many fleets this turn's fleet step would buy with ``treasury`` and ``planets``."""
        room = max(game.config.fleet_limit - corp.fleets, 0)
        bought = 0
        for price in next_fleet_prices(game, room):
            if treasury < price or not self._wants_fleet(
                game, forecast, corp.fleets + bought, planets, contract_value, price
            ):
                break
            treasury -= price
            bought += 1
        return bought

    @staticmethod
    def _capped_revenue(
        game: Game, planets: list[Planet], max_pairs: int, contract_value: int
    ) -> int:
        return compute_revenue(
            planets, game.config, contract_value=contract_value, max_pairs=max_pairs
        ).total

    def _build_reserve(self, game: Game, forecast: TrackForecast, corp: Corporation) -> int:
        """Treasury no build may spend: the mandatory first fleet if the corporation has none,
        the replacement a seizure could make necessary, and the policy's war chest."""
        if corp.fleets == 0:
            # It will run one pair once it has bought the mandatory fleet.
            revenue = self._capped_revenue(
                game, game.reachable_planets(corp), 1, game.contract_value()
            )
            survival = game.fleet_price() + forecast.fleet_reserve(1, revenue)
        else:
            survival = forecast.fleet_reserve(
                corp.fleets, self._lasting_revenue(game, forecast, corp)
            )
        chest = int(self.policy.treasury_reserve_fleets * forecast.cautious_price)
        return max(survival, chest)

    @staticmethod
    def _lasting_revenue(game: Game, forecast: TrackForecast, corp: Corporation) -> int:
        """Revenue a turn the corporation can count on until the next seizure: its current
        revenue, less its contract pairs if the site is expected to move away first."""
        result = game.revenue(corp)
        if forecast.rounds_to_site_move >= forecast.seizure_deadline:
            return result.total
        return result.total - sum(p.value for p in result.pairs if p.contract)

    def _site_weight(self, game: Game, forecast: TrackForecast) -> float:
        """How much builds value the active site now: ``contract_weight``, discounted by the
        share of the game's remaining turns the site will still be there."""
        weight = self.policy.contract_weight
        if weight == 0 or game.death_star_site() is None or forecast.turns_left <= 0:
            return 0.0
        return weight * min(1.0, forecast.site_turns_left / forecast.turns_left)

    def _planning_view(
        self, game: Game, site_weight: float, planets: list[Planet]
    ) -> tuple[list[Planet], int]:
        """The planets and contract value builds are valued with: the site's contracts
        weighted by ``site_weight``, and the site left out entirely at weight 0."""
        site = game.death_star_site()
        if site_weight == 0 and site is not None:
            planets = [p for p in planets if p.hex != site]
        return planets, round(game.contract_value() * site_weight)

    def _death_star_gains(
        self,
        game: Game,
        forecast: TrackForecast,
        corp: Corporation,
        candidates: Sequence[NetworkAction],
        reach: frozenset[Hex],
    ) -> list[int]:
        """Each build's revenue gain under the pair cap it would really have this turn: the
        fleets owned plus those the fleet step would buy with what the build leaves."""
        weight = self._site_weight(game, forecast)
        planets, contract_value = self._planning_view(game, weight, game.reachable_planets(corp))
        fleets = corp.fleets + self._fleets_to_buy(
            game, forecast, corp, corp.treasury, planets, contract_value
        )
        current = self._capped_revenue(game, planets, fleets, contract_value)
        gains = []
        for action in candidates:
            after, _ = self._planning_view(
                game, weight, self._planets_after(game, corp, action, reach)
            )
            fleets = corp.fleets + self._fleets_to_buy(
                game, forecast, corp, corp.treasury - action.cost, after, contract_value
            )
            gains.append(self._capped_revenue(game, after, fleets, contract_value) - current)
        return gains

    def _death_star_targets(
        self, game: Game, forecast: TrackForecast, reach: frozenset[Hex]
    ) -> dict[Hex, float]:
        """Where builds head, each target with a weight: 1 for an unreached planet, and for a
        construction site how much it is valued, so a site of weight 2 is aimed at as if half as
        far. The active site is left out at weight 0; the reserved next site counts only once
        the site is expected to move within ``RESERVED_SITE_LEAD_TURNS``, weighted by the share
        of the remaining turns it will then have."""
        site = game.death_star_site()
        targets: dict[Hex, float] = {
            p.hex: 1.0 for p in game.board.planets if p.hex not in reach and p.hex != site
        }
        weight = self._site_weight(game, forecast)
        if site is not None and site not in reach and weight > 0:
            targets[site] = weight
        reserved = game.death_star_reserved_sites()
        to_move = forecast.rounds_to_site_move
        turns = forecast.turns_left
        if (
            reserved
            and self.policy.contract_weight > 0
            and to_move <= RESERVED_SITE_LEAD_TURNS
            and turns > to_move
        ):
            targets[reserved[0]] = self.policy.contract_weight * (turns - to_move) / turns
        return targets

    def _rush_bonuses(
        self,
        game: Game,
        forecast: TrackForecast,
        corp: Corporation,
        candidates: Sequence[NetworkAction],
        reach: frozenset[Hex],
        blocked: frozenset[Hex],
    ) -> list[float]:
        """Extra gain, in revenue units, for builds that bring an unreached active site closer,
        for a policy that values the site above a planet (site weight w > 1): (w - 1) times the
        contract value per chart's worth (or hex, with straight routing) of progress. All 0
        otherwise."""
        site = game.death_star_site()
        eagerness = self._site_weight(game, forecast) - 1
        if site is None or site in reach or eagerness <= 0:
            return [0.0] * len(candidates)
        per_unit = eagerness * game.contract_value()
        if self.policy.routing == "path":
            to_site = self._route_map(
                game,
                corp,
                dict(self._route_costs(game, corp, [site], blocked)),
                {site: 1.0},
                blocked,
            )
            start = to_site.from_network(reach)
            now = NO_ROUTE_COST if start is None else start
            unit = game.config.chart_cost
            after = [self._remaining_route_cost(game, a, reach, to_site) for a in candidates]
        else:
            frontier = {
                n
                for h in reach
                for _, n in game.board.neighbors(h)
                if n not in reach and not game.board.is_planet(n)
            }
            now = min((h.distance(site) for h in frontier), default=0)
            unit = 1
            after = [self._straight_distance(a, {site: 1.0}) for a in candidates]
        return [per_unit * max(0.0, now - left) / unit for left in after]

    def _blocked_hexes(self, game: Game) -> frozenset[Hex]:
        """Hexes routes may not pass through: reserved sites, which cannot be charted, and the
        active site for a policy that will not go near it."""
        blocked = set(game.death_star_reserved_sites())
        site = game.death_star_site()
        if site is not None and self.policy.contract_weight == 0:
            blocked.add(site)
        return frozenset(blocked)

    def _intended_death_star_dividend(self, game: Game, corp: Corporation, revenue: int) -> bool:
        """The dividend decision under the Death Star rules.

        Survival comes first: withhold while the treasury is below the fleet reserve or the
        policy's war chest. The rest is judged on what builds may spend: the treasury less that
        reserve (``_build_reserve``).

        - ``withhold_for_builds`` withholds exactly when the corporation wants a fleet it cannot
          pay for, or a build that would raise revenue costs more than it may spend.
        - Otherwise it pays once it may spend ``pay_threshold`` charts' worth, the cushion.
          Below that it withholds only while there is something to spend the cash on soon:
          what ``withhold_for_builds`` would withhold for, or a planet that would raise revenue
          and that the cushion would pay to reach (``_gaining_connection_within``). Paying when
          nothing needs the money avoids withholding turn after turn for builds that are never
          made, or that only add planets its fleets cannot run.
        """
        forecast = TrackForecast.of(game)
        if corp.treasury < forecast.fleet_reserve(
            corp.fleets, self._lasting_revenue(game, forecast, corp)
        ):
            return False
        if corp.treasury < self.policy.treasury_reserve_fleets * forecast.cautious_price:
            return False
        steps = self.policy.pay_when_steps
        if steps and game.payout_steps(revenue, game.price(corp)) >= steps:
            return True
        if game.round_number < self.policy.withhold_until_round:
            return False
        spendable = corp.treasury - self._build_reserve(game, forecast, corp)
        if self.policy.withhold_for_builds:
            return not self._needs_cash_death_star(game, forecast, corp, spendable)
        if revenue < self.policy.withhold_when_revenue_below:
            return False
        target = game.config.chart_cost * self.policy.pay_threshold
        # A zero target (the always-pay policies) pays whatever the reserve.
        if target == 0 or spendable >= target:
            return True
        if self._needs_cash_death_star(game, forecast, corp, spendable):
            return False
        return not self._gaining_connection_within(game, forecast, corp, target)

    def _wants_unaffordable_fleet(
        self, game: Game, forecast: TrackForecast, corp: Corporation
    ) -> bool:
        """Whether this policy wants another fleet that the treasury cannot pay for. Under the
        facility rules: whether the facility step would build one if it could pay
        (``_facility_choice``)."""
        price = game.fleet_price()
        if corp.fleets >= game.config.fleet_limit or price <= corp.treasury:
            return False
        if game.config.facility_rules:
            rich = copy.copy(corp)
            rich.treasury = 10**9
            builds = game.legal_facility_builds(rich)
            return self._facility_choice(game, forecast, corp, builds) is not None
        weight = self._site_weight(game, forecast)
        planets, contract_value = self._planning_view(game, weight, game.reachable_planets(corp))
        return self._wants_fleet(game, forecast, corp.fleets, planets, contract_value, price)

    def _gaining_connection_within(
        self, game: Game, forecast: TrackForecast, corp: Corporation, budget: int
    ) -> bool:
        """Whether ``budget`` would pay for reaching an unreached planet (or the construction
        site, valued as when planning builds) that raises revenue: a route from the network to a
        planet that gains with the fleets the corporation owns, or a route plus one more fleet
        at the cautious price to a planet that gains only with that fleet."""
        weight = self._site_weight(game, forecast)
        reach = game.reachable(corp)
        planets, contract_value = self._planning_view(game, weight, game.reachable_planets(corp))
        fleets = corp.fleets
        now = self._capped_revenue(game, planets, fleets, contract_value)
        more = fleets < game.config.fleet_limit
        # A planet gains "with a fleet" only beyond what the fleet alone would add.
        fleet_alone = (
            max(now, self._capped_revenue(game, planets, fleets + 1, contract_value))
            if more
            else now
        )
        gaining: list[Hex] = []
        gaining_with_fleet: list[Hex] = []
        for planet in game.board.planets:
            if planet.hex in reach:
                continue
            after, _ = self._planning_view(game, weight, planets + [planet])
            if self._capped_revenue(game, after, fleets, contract_value) > now:
                gaining.append(planet.hex)
            elif more and self._capped_revenue(game, after, fleets + 1, contract_value) > (
                fleet_alone
            ):
                gaining_with_fleet.append(planet.hex)
        blocked = self._blocked_hexes(game)
        for targets, route_budget in (
            (gaining, budget),
            (gaining_with_fleet, budget - forecast.cautious_price),
        ):
            if not targets or route_budget <= 0:
                continue
            # A route's cost counts every hex it enters, the first beside the network included.
            to_go = self._route_map(
                game,
                corp,
                dict(self._route_costs(game, corp, targets, blocked)),
                dict.fromkeys(targets, 1.0),
                blocked,
            )
            route = to_go.from_network(reach)
            if route is not None and route <= route_budget:
                return True
        return False

    def _needs_cash_death_star(
        self, game: Game, forecast: TrackForecast, corp: Corporation, budget: int
    ) -> bool:
        """Whether the treasury cannot pay for a fleet this policy wants, or a build costing
        more than ``budget`` would raise revenue with the fleets the corporation owns."""
        if self._wants_unaffordable_fleet(game, forecast, corp):
            return True
        weight = self._site_weight(game, forecast)
        planets, contract_value = self._planning_view(game, weight, game.reachable_planets(corp))
        unlimited = copy.copy(corp)
        unlimited.treasury = 10**9
        reach = game.reachable(corp)
        current = self._capped_revenue(game, planets, corp.fleets, contract_value)
        for action in game.legal_network_actions(unlimited):
            if isinstance(action, NoNetworkAction) or action.cost <= budget:
                continue
            after, _ = self._planning_view(
                game, weight, self._planets_after(game, corp, action, reach)
            )
            if self._capped_revenue(game, after, corp.fleets, contract_value) > current:
                return True
        return False


@dataclass(frozen=True)
class _FacilityOption:
    """One legal facility build, as ``GreedyBot._choose_facility`` values it."""

    action: BuildFacility
    revenue_now: int
    """Planning revenue a turn now, with the facilities owned."""
    marginal: int
    """Planning revenue a turn after the build, with one more pair and whatever planets the new
    exit connects, less ``revenue_now``."""
    route_saving: float
    """How much cheaper the build makes the cheapest route from the network to a target."""
    opening: float
    """The cheapest route out of the network from the planet, if the new exit made it cheaper;
    ``NO_ROUTE_COST`` if it opened nothing (see ``GreedyBot._exit_opening``)."""
    gift: int
    """0: the new exit goes to the builder's own dangling lane; 1: left unclaimed; 2: given to
    a lane only rivals serve."""
    site_distance: int
    """Hexes from the planet to the construction site (0 with no site)."""


def _weighted(cost: int, weight: float) -> float:
    """``cost`` as it counts toward a target of ``weight``: unchanged at weight 1."""
    return cost if weight == 1 else cost / weight


def _is_first_par(action: BuyShare, buys: list[BuyShare]) -> bool:
    """Whether ``action`` is the first listed start option for its corporation."""
    return next(b for b in buys if b.corp_id == action.corp_id) is action
