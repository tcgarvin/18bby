"""Game state and rule enforcement for stock rounds and operating rounds.

The ``Game`` owns all state and exposes legality queries plus mutation methods. Drivers
(bots, a CLI, a future web API) decide *what* to do; this module decides whether it is
legal and applies the consequences.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import combinations

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
from bby18.board import Board, Planet, load_board
from bby18.config import DEFAULT_CONFIG, GameConfig
from bby18.hexgrid import Hex
from bby18.market import StockMarket
from bby18.network import HyperspaceNetwork, IllegalAction
from bby18.revenue import RevenueResult, compute_revenue
from bby18.state import NO_PLAYER, Corporation, CorpStatus, Player


@dataclass
class LogEntry:
    round_label: str
    actor: str
    text: str

    def __str__(self) -> str:
        return f"[{self.round_label}] {self.actor}: {self.text}"


@dataclass
class Game:
    config: GameConfig
    board: Board
    players: list[Player]
    corporations: dict[str, Corporation]
    network: HyperspaceNetwork
    market: StockMarket
    bank: int = 0
    round_number: int = 0
    round_label: str = "setup"
    priority_player: int = 0
    stock_rounds_played: int = 0
    log: list[LogEntry] = field(default_factory=list)
    _floats: int = 0

    @classmethod
    def new(cls, player_names: list[str], config: GameConfig = DEFAULT_CONFIG) -> Game:
        config.validate_rule_variants()
        board = load_board(config.map_file)
        cash = config.starting_cash(len(player_names))
        players = [Player(f"P{i + 1}", name, cash) for i, name in enumerate(player_names)]
        corporations = {}
        for spec in config.corporations:
            board.planet_named(spec.homeworld)  # validates the homeworld exists
            corporations[spec.id] = Corporation(spec, ipo_shares=config.shares_per_corporation)
        return cls(
            config=config,
            board=board,
            players=players,
            corporations=corporations,
            network=HyperspaceNetwork(board),
            market=StockMarket(config),
        )

    # --- helpers -------------------------------------------------------------

    def player(self, player_id: str) -> Player:
        for p in self.players:
            if p.id == player_id:
                return p
        raise KeyError(f"No player {player_id}")

    def corp(self, corp_id: str) -> Corporation:
        try:
            return self.corporations[corp_id]
        except KeyError:
            raise KeyError(f"No corporation {corp_id}") from None

    def price(self, corp: Corporation) -> int:
        return self.market.price_at(corp.market_cell)

    def homeworld(self, corp: Corporation) -> Hex:
        return self.board.planet_named(corp.spec.homeworld).hex

    def reachable(self, corp: Corporation) -> frozenset[Hex]:
        return self.network.reachable(corp.id, self.homeworld(corp))

    def reachable_planets(self, corp: Corporation) -> list[Planet]:
        return [
            self.board.planet_at(h) for h in sorted(self.reachable(corp)) if self.board.is_planet(h)
        ]

    def revenue(self, corp: Corporation) -> RevenueResult:
        result = compute_revenue(self.reachable_planets(corp), self.config)
        if self.config.homeworld_basic_income > 0:
            result = replace(result, floor=self.config.homeworld_basic_income)
        return result

    def ipo_price(self, corp: Corporation) -> int:
        """What one IPO share of a started corporation costs now."""
        if self.config.ipo_price_rule == "market_after_float" and corp.floated:
            return max(corp.par, self.price(corp))
        return corp.par

    def certificate_count(self, player: Player) -> int:
        count = 0
        for corp_id, shares in player.shares.items():
            if shares == 0:
                continue
            count += shares - (1 if self.corp(corp_id).president == player.id else 0)
        return count

    def operating_order(self) -> list[Corporation]:
        floated = [c for c in self.corporations.values() if c.floated]
        return sorted(floated, key=lambda c: (-self.price(c), c.float_order))

    def _log(self, actor: str, text: str) -> None:
        self.log.append(LogEntry(self.round_label, actor, text))

    # --- stock round -----------------------------------------------------------

    def legal_stock_actions(self, player: Player, sold_this_round: set[str]) -> list[StockAction]:
        actions: list[StockAction] = [PassStock()]
        can_buy = self.certificate_count(player) < self.config.certificate_limit
        for corp in self.corporations.values():
            if corp.status is CorpStatus.UNSTARTED:
                if can_buy and corp.id not in sold_this_round:
                    for par in self.config.par_prices:
                        if player.cash >= par * self.config.president_share_size:
                            actions.append(BuyShare(corp.id, ShareSource.IPO, par))
                continue
            if not can_buy or corp.id in sold_this_round:
                pass
            elif player.shares_in(corp.id) < self.config.max_holding_shares:
                if corp.ipo_shares > 0 and player.cash >= self.ipo_price(corp):
                    actions.append(BuyShare(corp.id, ShareSource.IPO))
                if corp.pool_shares > 0 and player.cash >= self.price(corp):
                    actions.append(BuyShare(corp.id, ShareSource.POOL))
            if self.stock_rounds_played > 0:
                for count in range(1, player.shares_in(corp.id) + 1):
                    if self._can_sell(player, corp, count):
                        actions.append(SellShares(corp.id, count))
        return actions

    def _can_sell(self, player: Player, corp: Corporation, count: int) -> bool:
        held = player.shares_in(corp.id)
        if count < 1 or count > held:
            return False
        if corp.pool_shares + count > self.config.shares_per_corporation // 2:
            return False
        if corp.president != player.id:
            return True
        remaining = held - count
        if remaining >= self.config.president_share_size:
            return True
        # The president may sell out only if someone else can take the presidency.
        return any(
            p.id != player.id and p.shares_in(corp.id) >= self.config.president_share_size
            for p in self.players
        )

    def apply_stock_action(
        self, player: Player, action: StockAction, sold_this_round: set[str]
    ) -> None:
        if isinstance(action, PassStock):
            self._log(player.name, "passes")
            return
        if isinstance(action, BuyShare):
            self._buy(player, action, sold_this_round)
            return
        if isinstance(action, SellShares):
            self._sell(player, action, sold_this_round)
            return
        raise IllegalAction(f"Unknown stock action {action!r}")

    def _buy(self, player: Player, action: BuyShare, sold_this_round: set[str]) -> None:
        corp = self.corp(action.corp_id)
        if action.corp_id in sold_this_round:
            raise IllegalAction(f"{player.name} sold {corp.id} this round and cannot buy it")
        if self.certificate_count(player) >= self.config.certificate_limit:
            raise IllegalAction(f"{player.name} is at the certificate limit")
        if corp.status is CorpStatus.UNSTARTED:
            if action.source is not ShareSource.IPO:
                raise IllegalAction(f"{corp.id} has not started; buy from the IPO")
            if action.par not in self.config.par_prices:
                raise IllegalAction(f"Par {action.par} is not an allowed par price")
            cost = action.par * self.config.president_share_size
            if player.cash < cost:
                raise IllegalAction(f"{player.name} cannot afford the president's share")
            corp.status = CorpStatus.PARRED
            corp.par = action.par
            corp.market_cell = self.market.par_cell(action.par)
            corp.president = player.id
            corp.ipo_shares -= self.config.president_share_size
            player.cash -= cost
            self.bank += cost
            self._capitalize(corp, self.config.president_share_size)
            player.shares[corp.id] = player.shares_in(corp.id) + self.config.president_share_size
            self._log(player.name, f"starts {corp.id} at par {action.par}")
            self._maybe_float(corp)
            return
        if player.shares_in(corp.id) >= self.config.max_holding_shares:
            raise IllegalAction(f"{player.name} is at the holding limit for {corp.id}")
        if action.source is ShareSource.IPO:
            if corp.ipo_shares < 1:
                raise IllegalAction(f"{corp.id} has no IPO shares left")
            cost = self.ipo_price(corp)
            corp.ipo_shares -= 1
        else:
            if corp.pool_shares < 1:
                raise IllegalAction(f"{corp.id} has no shares in the pool")
            cost = self.price(corp)
            corp.pool_shares -= 1
        if player.cash < cost:
            raise IllegalAction(f"{player.name} cannot afford a share of {corp.id}")
        player.cash -= cost
        self.bank += cost
        if action.source is ShareSource.IPO:
            self._capitalize(corp, 1)
        player.shares[corp.id] = player.shares_in(corp.id) + 1
        self._log(player.name, f"buys {corp.id} from {action.source.value} for {cost}")
        self._check_presidency(corp)
        self._maybe_float(corp)

    def _sell(self, player: Player, action: SellShares, sold_this_round: set[str]) -> None:
        corp = self.corp(action.corp_id)
        if self.stock_rounds_played == 0:
            raise IllegalAction("No sales during the first stock round")
        if not self._can_sell(player, corp, action.count):
            raise IllegalAction(f"{player.name} cannot sell {action.count} of {corp.id}")
        proceeds = self.price(corp) * action.count
        player.cash += proceeds
        self.bank -= proceeds
        player.shares[corp.id] = player.shares_in(corp.id) - action.count
        corp.pool_shares += action.count
        corp.market_cell = self.market.down(corp.market_cell, action.count)
        sold_this_round.add(corp.id)
        self._log(
            player.name, f"sells {action.count} {corp.id} for {proceeds}; price {self.price(corp)}"
        )
        self._check_presidency(corp)

    def _check_presidency(self, corp: Corporation) -> None:
        current = self.player(corp.president)
        largest = max(self.players, key=lambda p: (p.shares_in(corp.id), p.id == current.id))
        if largest.id != current.id and largest.shares_in(corp.id) > current.shares_in(corp.id):
            corp.president = largest.id
            self._log(largest.name, f"becomes president of {corp.id}")

    def _capitalize(self, corp: Corporation, shares_sold: int) -> None:
        """Under incremental capitalization, the bank pays par per IPO share into the treasury.

        The buyer's cash has already gone to the bank, so the bank's net change is the buyer's
        cost minus par (zero when the share sold at par).
        """
        if self.config.capitalization == "incremental":
            amount = corp.par * shares_sold
            corp.treasury += amount
            self.bank -= amount

    def _maybe_float(self, corp: Corporation) -> None:
        sold = self.config.shares_per_corporation - corp.ipo_shares
        if corp.status is CorpStatus.PARRED and sold >= self.config.float_threshold_shares:
            corp.status = CorpStatus.FLOATED
            if self.config.capitalization == "full":
                corp.treasury = corp.par * self.config.float_capital_shares
                self.bank -= corp.treasury
            corp.float_order = self._floats
            self._floats += 1
            self._log(corp.id, f"floats with treasury {corp.treasury}")

    # --- operating round ---------------------------------------------------------

    def legal_network_actions(self, corp: Corporation) -> list[NetworkAction]:
        actions: list[NetworkAction] = [NoNetworkAction()]
        reach = self.reachable(corp)
        net = self.network
        frontier: set[Hex] = set()
        for h in reach:
            for _, n in self.board.neighbors(h):
                if not self.board.is_planet(n):
                    frontier.add(n)
        cfg = self.config
        for hex in sorted(frontier):
            if net.is_charted(hex):
                if hex not in net.service_of(corp.id) and corp.treasury >= cfg.service_cost:
                    try:
                        net.check_extend_service(corp.id, hex, reach)
                        actions.append(ExtendService(hex, cfg.service_cost))
                    except IllegalAction:
                        pass
            elif corp.treasury >= cfg.chart_cost:
                for pair in combinations(sorted(net.legal_exits(hex)), 2):
                    exits = frozenset(pair)
                    try:
                        net.check_chart(corp.id, hex, exits, reach)
                        actions.append(Chart(hex, exits, cfg.chart_cost))
                    except IllegalAction:
                        pass
        if corp.treasury >= cfg.upgrade_cost:
            for hex in sorted(reach & net.service_of(corp.id)):
                tile = net.tile_at(hex)
                if tile is None:
                    continue
                for new_exit in sorted(net.legal_exits(hex) - tile.exits):
                    try:
                        net.check_upgrade(corp.id, hex, new_exit, reach)
                        actions.append(Upgrade(hex, new_exit, cfg.upgrade_cost))
                    except IllegalAction:
                        pass
        return actions

    def apply_network_action(self, corp: Corporation, action: NetworkAction) -> None:
        if isinstance(action, NoNetworkAction):
            self._log(corp.id, "takes no network action")
            return
        reach = self.reachable(corp)
        if isinstance(action, Chart):
            cost = self.config.chart_cost
            self._require_treasury(corp, cost)
            self.network.chart(corp.id, action.hex, action.exits, reach)
        elif isinstance(action, Upgrade):
            cost = self.config.upgrade_cost
            self._require_treasury(corp, cost)
            self.network.upgrade(corp.id, action.hex, action.new_exit, reach)
        elif isinstance(action, ExtendService):
            cost = self.config.service_cost
            self._require_treasury(corp, cost)
            self.network.extend_service(corp.id, action.hex, reach)
        else:
            raise IllegalAction(f"Unknown network action {action!r}")
        corp.treasury -= cost
        self.bank += cost
        self._log(corp.id, f"{action} for {cost}")

    def _require_treasury(self, corp: Corporation, cost: int) -> None:
        if corp.treasury < cost:
            raise IllegalAction(f"{corp.id} cannot afford {cost} (treasury {corp.treasury})")

    def settle_revenue(self, corp: Corporation, pay: bool) -> RevenueResult:
        """Apply the operating turn's revenue.

        Withholding puts it all in the treasury and moves the price left one column. Paying
        gives each player-held share its per-share amount; shares in the IPO or pool earn
        nothing, and that money and any rounding remainder stay with the bank. The price moves
        right by ``payout_steps``.
        """
        result = self.revenue(corp)
        corp.last_revenue = result.total
        price_before = self.price(corp)
        if result.total == 0 or not pay:
            corp.treasury += result.total
            self.bank -= result.total
            if result.total > 0 or self.config.zero_revenue_moves_price:
                corp.market_cell = self.market.left(corp.market_cell)
            self._log(corp.id, f"withholds {result.total}; price {self.price(corp)}")
            return result
        per_share = result.total // self.config.shares_per_corporation
        for p in self.players:
            paid = per_share * p.shares_in(corp.id)
            p.cash += paid
            self.bank -= paid
        corp.market_cell = self.market.right(
            corp.market_cell, self.payout_steps(result.total, price_before)
        )
        self._log(corp.id, f"pays {result.total} ({per_share}/share); price {self.price(corp)}")
        return result

    def payout_steps(self, revenue: int, price: int) -> int:
        """Columns to move right for paying out ``revenue`` at share price ``price``."""
        return sum(1 for f in self.config.payout_step_fractions if revenue >= price * f)

    def finish_stock_round(self) -> None:
        """End-of-stock-round market moves: a started corporation with no shares left in the
        IPO or the pool is sold out and moves up one row."""
        self.stock_rounds_played += 1
        for corp in self.corporations.values():
            if corp.status is CorpStatus.UNSTARTED:
                continue
            if corp.ipo_shares == 0 and corp.pool_shares == 0:
                corp.market_cell = self.market.up(corp.market_cell)
                self._log(corp.id, f"is sold out; price {self.price(corp)}")

    # --- scoring -------------------------------------------------------------------

    def player_worth(self, player: Player) -> int:
        worth = player.cash
        for corp_id, n in player.shares.items():
            worth += n * self.price(self.corp(corp_id))
        return worth

    def is_over(self) -> bool:
        return self.round_number >= self.config.total_rounds
