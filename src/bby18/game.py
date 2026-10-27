"""Game state and rule enforcement for stock rounds and operating rounds.

The ``Game`` owns all state and exposes legality queries plus mutation methods. Drivers
(bots, a CLI, a future web API) decide *what* to do; this module decides whether it is
legal and applies the consequences.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import combinations

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
from bby18.board import Board, Planet, Terrain, load_board
from bby18.config import COMPLETION, DEFAULT_CONFIG, SEIZURE, SITE_MOVE, GameConfig
from bby18.death_star import (
    SITE_NAME,
    DeathStarTrack,
    describe_result,
    fleet_price,
    fleet_tier_index,
    place_sites,
    site_planet,
    stage_name,
)
from bby18.hexgrid import Direction, Hex
from bby18.market import StockMarket
from bby18.network import HyperspaceNetwork, IllegalAction
from bby18.revenue import NO_PAIR_LIMIT, RevenueResult, compute_revenue
from bby18.state import NO_PLAYER, Corporation, CorpStatus, Facility, Player
from bby18.terrain import generate_terrain

EMPIRE = "Empire"
"""Log actor for Death Star track events and the fleet supply, and the owner of seized
facilities."""
UNFLOATED = (CorpStatus.UNSTARTED, CorpStatus.PARRED)
"""Statuses of a corporation that may still float (and so keeps a slot on its homeworld under
the facility rules)."""


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
    death_star: DeathStarTrack = field(default_factory=DeathStarTrack)
    """The construction sites and track; inactive unless ``config.death_star_rules``."""
    fleets_sold: int = 0
    """Fleets (or facilities, under the facility rules) sold from the shared supply so far.
    Free home facilities do not come from the supply."""
    facilities: list[Facility] = field(default_factory=list)
    """Every facility on the board, oldest first (experimental facility rules)."""
    facilities_built: int = 0
    """Facilities built so far, home facilities included: the next one's ``build_number``."""
    facility_seizure_ties: int = 0
    """Seizures at which a corporation's facilities nearest the site lay on more than one
    planet, so the most-recently-built tie-break decided which planet the Empire took. Two on
    one planet are the same outcome and do not count."""

    @classmethod
    def new(
        cls, player_names: list[str], config: GameConfig = DEFAULT_CONFIG, seed: int = 0
    ) -> Game:
        """A fresh game. ``seed`` fixes the terrain layout (and, under the Death Star rules,
        the construction sites); the same seed gives the same sky."""
        config.validate_rule_variants()
        board = load_board(config.map_file)
        board = board.with_terrain(generate_terrain(board, seed, config))
        cash = config.starting_cash(len(player_names))
        players = [Player(f"P{i + 1}", name, cash) for i, name in enumerate(player_names)]
        corporations = {}
        for spec in config.corporations:
            board.planet_named(spec.homeworld)  # validates the homeworld exists
            corporations[spec.id] = Corporation(spec, ipo_shares=config.shares_per_corporation)
        network = HyperspaceNetwork(board)
        if config.facility_rules:
            # The construction site is not on this board yet; it keeps every exit.
            network.limit_planet_exits((p.hex for p in board.planets), config.planet_base_exits)
        game = cls(
            config=config,
            board=board,
            players=players,
            corporations=corporations,
            network=network,
            market=StockMarket(config),
        )
        if config.death_star_rules:
            game.death_star = DeathStarTrack(
                sites=place_sites(board, seed, config),
                final_round=config.death_star_backstop_rounds,
            )
            game._place_site_on_board()
            first, second = game.death_star.sites
            game._log(
                EMPIRE,
                f"begins the Death Star at {first} ({game.board.region_of(first)}); the site "
                f"will move to {second} ({board.region_of(second)}), reserved until then",
            )
        return game

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
        """This turn's revenue: the best matching of the reachable planets, using at most one
        pair per fleet under the Death Star rules."""
        result = self.planet_revenue(self.reachable_planets(corp), self.pair_cap(corp))
        if self.config.homeworld_basic_income > 0:
            result = replace(result, floor=self.config.homeworld_basic_income)
        return result

    def planet_revenue(
        self, planets: list[Planet], max_pairs: int = NO_PAIR_LIMIT
    ) -> RevenueResult:
        """Pair revenue of ``planets`` at the current contract value, using at most
        ``max_pairs`` pairs, without the experimental income floor. For what-if evaluation."""
        return compute_revenue(
            planets, self.config, contract_value=self.contract_value(), max_pairs=max_pairs
        )

    def pair_cap(self, corp: Corporation) -> int:
        """Most pairs ``corp`` may run: its fleets under the Death Star rules (its facilities
        under the facility rules), else no cap."""
        return corp.fleets if self.config.death_star_rules else NO_PAIR_LIMIT

    def chart_cost(self, hex: Hex) -> int:
        """What charting ``hex`` costs: nebulae carry a surcharge."""
        cost = self.config.chart_cost
        if self.board.terrain_at(hex) is Terrain.NEBULA:
            cost += self.config.nebula_chart_surcharge
        return cost

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

    def closed_corporations(self) -> list[Corporation]:
        """Corporations that went bankrupt (experimental Death Star rules)."""
        return [c for c in self.corporations.values() if c.status is CorpStatus.CLOSED]

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
            if corp.status is CorpStatus.CLOSED:
                continue
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
        if corp.status is CorpStatus.CLOSED:
            raise IllegalAction(f"{corp.id} is closed; its shares have left the game")
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
            if self.config.facility_rules:
                self._place_home_facility(corp)

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
            elif corp.treasury >= self.chart_cost(hex):
                for pair in combinations(sorted(net.legal_exits(hex)), 2):
                    exits = frozenset(pair)
                    try:
                        net.check_chart(corp.id, hex, exits, reach)
                        actions.append(Chart(hex, exits, self.chart_cost(hex)))
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
        placed: frozenset[Direction] = frozenset()
        claimed: frozenset[Hex] = frozenset()
        if isinstance(action, Chart):
            cost = self.chart_cost(action.hex)
            self._require_treasury(corp, cost)
            claimed = self.network.chart(corp.id, action.hex, action.exits, reach)
            placed = action.exits
        elif isinstance(action, Upgrade):
            cost = self.config.upgrade_cost
            self._require_treasury(corp, cost)
            claimed = self.network.upgrade(corp.id, action.hex, action.new_exit, reach)
            placed = frozenset({action.new_exit})
        elif isinstance(action, ExtendService):
            cost = self.config.service_cost
            self._require_treasury(corp, cost)
            self.network.extend_service(corp.id, action.hex, reach)
        else:
            raise IllegalAction(f"Unknown network action {action!r}")
        corp.treasury -= cost
        self.bank += cost
        notes = self._planet_exit_notes(action.hex, placed, claimed)
        self._log(corp.id, f"{action} for {cost}{notes}")

    def _planet_exit_notes(
        self, hex: Hex, placed: frozenset[Direction], claimed: frozenset[Hex]
    ) -> str:
        """Log text for what new exits ``placed`` on the tile at ``hex`` did at exit-limited
        planets: claimed an exit there, or dangle. Empty without the facility rules."""
        notes = []
        for direction in sorted(placed):
            neighbor = hex.neighbor(direction)
            if not self.network.has_exit_limit(neighbor):
                continue
            name = self.board.planet_at(neighbor).name
            if neighbor in claimed:
                notes.append(f"claims an exit of {name}")
            else:
                notes.append(f"its exit toward {name} dangles")
        return "".join(f"; {note}" for note in notes)

    def _require_treasury(self, corp: Corporation, cost: int) -> None:
        if corp.treasury < cost:
            raise IllegalAction(f"{corp.id} cannot afford {cost} (treasury {corp.treasury})")

    def settle_revenue(self, corp: Corporation, pay: bool) -> RevenueResult:
        """Apply the operating turn's revenue.

        Withholding puts it all in the treasury and moves the price left one column. Paying
        gives each player-held share its per-share amount; shares in the IPO or pool earn
        nothing, and that money and any rounding remainder stay with the bank. The price moves
        right by ``payout_steps``. Under the Death Star rules each contract pair scored puts a
        cube on the track, whether the revenue is paid or withheld.
        """
        result = self.revenue(corp)
        corp.last_revenue = result.total
        price_before = self.price(corp)
        if self.config.death_star_rules and result.contract_pairs:
            self._add_cubes(corp.id, result.contract_pairs)
        if result.total == 0 or not pay:
            corp.treasury += result.total
            self.bank -= result.total
            moves = (
                self.config.withhold_moves_price
                if result.total > 0
                else self.config.zero_revenue_moves_price
            )
            if moves:
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
        IPO or the pool is sold out and moves up one row. Under the Death Star rules the Empire
        then adds its cubes to the track (``resolve_death_star`` applies any stage filled)."""
        self.stock_rounds_played += 1
        for corp in self.corporations.values():
            if corp.status in (CorpStatus.UNSTARTED, CorpStatus.CLOSED):
                continue
            if corp.ipo_shares == 0 and corp.pool_shares == 0:
                corp.market_cell = self.market.up(corp.market_cell)
                self._log(corp.id, f"is sold out; price {self.price(corp)}")
        if self.config.death_star_rules and self.config.empire_cubes_per_stock_round > 0:
            self._add_cubes(EMPIRE, self.config.empire_cubes_per_stock_round)

    # --- fleets and bankruptcy (experimental Death Star rules) -------------------

    def fleet_price(self) -> int:
        """What the next fleet from the shared supply costs."""
        return fleet_price(self.config.fleet_tiers, self.fleets_sold)

    def fleet_tier(self) -> int:
        """Index in ``config.fleet_tiers`` of the tier the next fleet comes from."""
        return fleet_tier_index(self.config.fleet_tiers, self.fleets_sold)

    def legal_fleet_actions(self, corp: Corporation) -> list[FleetAction]:
        """A corporation's options in its fleet step: buy one more fleet if it is under the
        limit and can pay, and finish once it owns at least one. Empty means it is bankrupt
        (see ``must_close``). Under the facility rules the step builds facilities instead (see
        ``legal_facility_builds``)."""
        self._require_death_star_rules()
        actions: list[FleetAction] = []
        if self.config.facility_rules:
            actions.extend(self.legal_facility_builds(corp))
        else:
            price = self.fleet_price()
            if corp.fleets < self.config.fleet_limit and corp.treasury >= price:
                actions.append(BuyFleet(price))
        if corp.fleets >= 1:
            actions.append(FinishFleets())
        return actions

    def apply_fleet_action(self, corp: Corporation, action: FleetAction) -> None:
        """Buy one fleet (or, under the facility rules, build one facility) at the current
        price, or finish the step."""
        self._require_death_star_rules()
        facility_rules = self.config.facility_rules
        if isinstance(action, FinishFleets):
            noun = "facility" if facility_rules else "fleet"
            if corp.fleets < 1:
                raise IllegalAction(f"{corp.id} must own a {noun} before finishing")
            if facility_rules:
                self._log(corp.id, f"finishes building facilities with {corp.fleets}")
            else:
                self._log(corp.id, f"finishes buying fleets with {corp.fleets}")
            return
        if facility_rules:
            if not isinstance(action, BuildFacility):
                raise IllegalAction(f"Under the facility rules {action!r} is not a legal move")
            self._build_facility(corp, action)
            return
        if not isinstance(action, BuyFleet):
            raise IllegalAction(f"Unknown fleet action {action!r}")
        price = self.fleet_price()
        if action.cost != price:
            raise IllegalAction(f"A fleet costs {price} now, not {action.cost}")
        if corp.fleets >= self.config.fleet_limit:
            raise IllegalAction(f"{corp.id} already owns {corp.fleets} fleets, the limit")
        self._require_treasury(corp, price)
        corp.treasury -= price
        self.bank += price
        corp.fleets += 1
        self.fleets_sold += 1
        self._log(corp.id, f"buys a fleet for {price}; owns {corp.fleets}")
        if self.fleet_price() != price:
            self._log(EMPIRE, f"fleet price rises to {self.fleet_price()}")

    def must_close(self, corp: Corporation) -> bool:
        """Whether ``corp``, at its fleet step, is bankrupt: it owns no fleet and its treasury
        cannot pay the current fleet price. Under the facility rules: it owns no facility and
        cannot build one (no money, or no planet it may build on)."""
        if not (self.config.death_star_rules and corp.floated and corp.fleets == 0):
            return False
        if self.config.facility_rules:
            return not self.legal_facility_builds(corp)
        return corp.treasury < self.fleet_price()

    def close_bankrupt(self, corp: Corporation) -> None:
        """Close a bankrupt corporation for good.

        Its shares leave the game (worth 0 to every holder, nobody pays), its treasury goes to
        the bank, and it loses its service; its tiles stay on the board for everyone else. It
        never operates, trades or counts toward a certificate limit again.
        """
        if not self.must_close(corp):
            raise IllegalAction(f"{corp.id} is not bankrupt")
        treasury = corp.treasury
        price = self.fleet_price()
        for player in self.players:
            player.shares.pop(corp.id, None)
        corp.status = CorpStatus.CLOSED
        corp.ipo_shares = 0
        corp.pool_shares = 0
        corp.president = NO_PLAYER
        corp.last_revenue = 0
        self.bank += treasury
        corp.treasury = 0
        self.network.remove_service(corp.id)
        if not self.config.facility_rules:
            reason = f"no fleet, and its treasury of {treasury} cannot buy one at {price}"
        elif treasury < price:
            reason = f"no facility, and its treasury of {treasury} cannot build one at {price}"
        else:
            reason = "no facility, and no planet it may build one on"
        self._log(
            corp.id,
            f"is bankrupt: {reason}. It closes; its shares are worthless and its tiles stay for "
            "others",
        )

    def _require_death_star_rules(self) -> None:
        if not self.config.death_star_rules:
            raise IllegalAction("Fleets exist only under the Death Star rules")

    # --- facilities and planet exits (experimental facility rules) ---------------

    def facilities_on(self, planet: Hex) -> list[Facility]:
        """The facilities on ``planet``, corporate and Imperial, oldest first."""
        return [f for f in self.facilities if f.planet == planet]

    def facilities_of(self, corp: Corporation) -> list[Facility]:
        """The facilities ``corp`` owns, oldest first."""
        return [f for f in self.facilities if f.owner == corp.id]

    def free_facility_slots(self, planet: Hex) -> int:
        """Facilities a floated corporation may still build on ``planet``: the per-planet limit,
        less the facilities there and one slot kept on the homeworld of each corporation that
        has not floated yet."""
        reserved = sum(
            1
            for c in self.corporations.values()
            if c.status in UNFLOATED and self.homeworld(c) == planet
        )
        return self.config.facilities_per_planet - len(self.facilities_on(planet)) - reserved

    def facility_planets(self, corp: Corporation) -> list[Hex]:
        """Planets ``corp`` may build a facility on, money and the facility limit aside: those
        with a free slot that it reaches, that one of its served, reachable tiles has an exit
        facing (a dangling lane), or that hold one of its facilities. Never the construction
        site, whose exits are not limited."""
        return sorted(h for h in self._facility_access(corp) if self.free_facility_slots(h) > 0)

    def _facility_access(self, corp: Corporation) -> set[Hex]:
        """Exit-limited planets ``corp`` reaches, points a served, reachable tile at, or holds
        a facility on, whether or not they have a free slot."""
        net = self.network
        reach = self.reachable(corp)
        planets = {h for h in reach if net.has_exit_limit(h)}
        for hex in reach:
            tile = net.tile_at(hex)
            if tile is None:
                continue
            for direction in tile.exits:
                neighbor = hex.neighbor(direction)
                if net.has_exit_limit(neighbor):
                    planets.add(neighbor)
        planets.update(f.planet for f in self.facilities_of(corp))
        return planets

    def legal_facility_builds(self, corp: Corporation) -> list[BuildFacility]:
        """Every facility ``corp`` could build now, if it is under the limit and can pay the
        current price: for each planet in ``facility_planets``, the new exit left unclaimed and
        the new exit given to each lane dangling there."""
        price = self.fleet_price()
        if corp.fleets >= self.config.fleet_limit or corp.treasury < price:
            return []
        builds = []
        for planet in self.facility_planets(corp):
            builds.append(BuildFacility(planet, None, price))
            for side in sorted(self.network.dangling_sides(planet)):
                builds.append(BuildFacility(planet, side, price))
        return builds

    def network_after_facility(self, action: BuildFacility) -> HyperspaceNetwork:
        """A copy of the network with the exit ``action`` would add, for what-if evaluation.
        Legality is not checked; the facility itself is not recorded."""
        net = self.network.copy()
        net.add_planet_exit(action.planet)
        if action.exit_side is not None:
            net.claim_exit(action.planet, action.exit_side)
        return net

    def _build_facility(self, corp: Corporation, action: BuildFacility) -> None:
        price = self.fleet_price()
        if action.cost != price:
            raise IllegalAction(f"A facility costs {price} now, not {action.cost}")
        if corp.fleets >= self.config.fleet_limit:
            raise IllegalAction(f"{corp.id} already owns {corp.fleets} facilities, the limit")
        self._require_treasury(corp, price)
        planet = action.planet
        if not self.network.has_exit_limit(planet):
            raise IllegalAction(f"{planet} is not a planet that can hold a facility")
        name = self.board.planet_at(planet).name
        if self.free_facility_slots(planet) < 1:
            raise IllegalAction(f"{name} has no free facility slot")
        if planet not in self._facility_access(corp):
            raise IllegalAction(
                f"{corp.id} neither reaches {name}, points a lane at it, nor has a facility there"
            )
        side = action.exit_side
        if side is not None and side not in self.network.dangling_sides(planet):
            raise IllegalAction(f"No lane dangles at {name} on side {side.name}")
        corp.treasury -= price
        self.bank += price
        self.fleets_sold += 1
        self._add_facility(corp, planet, side)
        where = "exit unclaimed" if side is None else f"exit toward {planet.neighbor(side)}"
        self._log(corp.id, f"builds a facility at {name} for {price} ({where}); owns {corp.fleets}")
        if self.fleet_price() != price:
            self._log(EMPIRE, f"facility price rises to {self.fleet_price()}")

    def _place_home_facility(self, corp: Corporation) -> None:
        """The free facility a corporation floats with, on its homeworld and outside the
        supply. Its homeworld kept a slot for it until now."""
        home = self.homeworld(corp)
        name = self.board.planet_at(home).name
        if self.free_facility_slots(home) < 1:
            raise ValueError(f"{name} has no slot left for {corp.id}'s home facility")
        self._add_facility(corp, home, None)
        self._log(corp.id, f"gets a free facility at {name}, its homeworld; owns {corp.fleets}")

    def _add_facility(self, corp: Corporation, planet: Hex, side: Direction | None) -> None:
        """Record a new facility of ``corp`` and give its planet the new exit, claimed for the
        lane on ``side`` or, with ``None``, left unclaimed."""
        self.facilities.append(Facility(planet, corp.id, self.facilities_built))
        self.facilities_built += 1
        self.network.add_planet_exit(planet)
        if side is not None:
            self.network.claim_exit(planet, side)
        corp.fleets += 1

    # --- the Death Star track (experimental Death Star rules) --------------------

    def death_star_site(self) -> Hex | None:
        """The hex of the construction site, or ``None`` when there is none on the board."""
        return self.death_star.active_site

    def death_star_reserved_sites(self) -> tuple[Hex, ...]:
        """Future construction sites: shown on the board but not yet chartable."""
        return self.death_star.reserved_sites

    def death_star_stage(self) -> int:
        """The 0-based index of the stage being built: stages whose result has applied."""
        return self.death_star.stages_resolved

    def contract_value(self) -> int:
        """What a contract pair scores now: the value of the stage being built, or 0 when no
        site is on the board."""
        if self.death_star.active_site is None:
            return 0
        return self.config.death_star_stage_values[self.death_star.stages_resolved]

    def _add_cubes(self, actor: str, count: int) -> None:
        track = self.death_star
        filled_before = track.stages_filled(self.config)
        track.cubes += count
        total = self.config.death_star_cubes_per_stage * len(self.config.death_star_stage_values)
        noun = "cube" if count == 1 else "cubes"
        self._log(actor, f"adds {count} {noun} to the Death Star track ({track.cubes}/{total})")
        for index in range(filled_before, track.stages_filled(self.config)):
            result = self.config.death_star_stage_results[index]
            self._log(
                EMPIRE,
                f"Death Star {stage_name(index)} is built: "
                f"{describe_result(result, self.config)} at the end of this round",
            )

    def resolve_death_star(self) -> None:
        """Apply, in order, the result of every stage filled but not yet resolved. The session
        calls this at the end of every operating round and stock round. Does nothing with the
        Death Star rules off."""
        if not self.config.death_star_rules:
            return
        track = self.death_star
        while track.stages_resolved < track.stages_filled(self.config):
            result = self.config.death_star_stage_results[track.stages_resolved]
            track.stages_resolved += 1
            if result == SEIZURE:
                self._seize_fleets()
            elif result == SITE_MOVE:
                self._move_site()
            elif result == COMPLETION:
                self._launch()
            else:
                raise ValueError(f"Unknown Death Star stage result {result!r}")

    def _seize_fleets(self) -> None:
        if self.config.facility_rules:
            self._seize_facilities()
            return
        seized = [c for c in self.corporations.values() if c.floated and c.fleets > 0]
        for corp in seized:
            corp.fleets -= 1
            self._log(EMPIRE, f"seizes a fleet from {corp.id}; it owns {corp.fleets}")
        if not seized:
            self._log(EMPIRE, "finds no fleets to seize")

    def _seize_facilities(self) -> None:
        """Each floated corporation with a facility loses the one nearest the construction site
        to the Empire, the most recently built on a tie. It stays on its planet, fills its slot
        and keeps its exit."""
        site = self.death_star.active_site
        if site is None:
            raise ValueError("A seizure needs a construction site on the board")
        seized_any = False
        for corp in self.corporations.values():
            owned = self.facilities_of(corp) if corp.floated else []
            if not owned:
                continue
            taken, tied = _seizure_choice(owned, site)
            if tied:
                self.facility_seizure_ties += 1
            self.facilities[self.facilities.index(taken)] = replace(taken, owner=EMPIRE)
            corp.fleets -= 1
            seized_any = True
            name = self.board.planet_at(taken.planet).name
            self._log(EMPIRE, f"takes over {corp.id}'s facility at {name}; it owns {corp.fleets}")
        if not seized_any:
            self._log(EMPIRE, "finds no facilities to take over")

    def facilities_to_seize(self) -> dict[str, Facility]:
        """The facility a seizure would take now from each floated corporation that owns one,
        by corporation id (see ``_seize_facilities``). Empty when no construction site is on
        the board, so no seizure can come."""
        site = self.death_star.active_site
        if site is None:
            return {}
        targets: dict[str, Facility] = {}
        for corp in self.corporations.values():
            owned = self.facilities_of(corp) if corp.floated else []
            if owned:
                targets[corp.id] = _seizure_choice(owned, site)[0]
        return targets

    def _move_site(self) -> None:
        track = self.death_star
        old = track.active_site
        if old is None or track.site_index + 1 >= len(track.sites):
            raise ValueError("The Death Star site has nowhere to move")
        track.site_index += 1
        self._place_site_on_board()
        new = track.sites[track.site_index]
        self._log(
            EMPIRE,
            f"moves the Death Star site from {old} to {new} ({self.board.region_of(new)}); "
            f"{old} is empty space",
        )

    def _launch(self) -> None:
        track = self.death_star
        old = track.active_site
        track.launched = True
        self._place_site_on_board()
        track.final_round = min(track.final_round, self.round_number + 1)
        where = f"; {old} is empty space" if old is not None else ""
        self._log(
            EMPIRE,
            f"launches the Death Star{where}. The game ends after this set of operating rounds",
        )

    def _place_site_on_board(self) -> None:
        """Rebuild the board so the active site, and only it, is a planet, and reserve the
        future sites in the network."""
        base = self.board
        if any(p.name == SITE_NAME for p in base.planets):
            base = base.without_planet(SITE_NAME)
        active = self.death_star.active_site
        board = base if active is None else base.with_planet(site_planet(base, active, self.config))
        self.board = board
        self.network.rebase(board, frozenset(self.death_star.reserved_sites))

    # --- scoring -------------------------------------------------------------------

    def player_worth(self, player: Player) -> int:
        worth = player.cash
        for corp_id, n in player.shares.items():
            worth += n * self.share_value(self.corp(corp_id))
        return worth

    def share_value(self, corp: Corporation) -> int:
        """What one share counts for in player worth: its price, plus a share of the treasury
        under the experimental ``treasury_in_final_worth`` rule."""
        fraction = self.config.treasury_in_final_worth
        claim = fraction * corp.treasury / self.config.shares_per_corporation
        return self.price(corp) + int(claim)

    def round_limit(self) -> int:
        """The last round the game can run to: ``total_rounds``, or under the Death Star rules
        the backstop (or the launch round, once the station has launched)."""
        if self.config.death_star_rules:
            return self.death_star.final_round
        return self.config.total_rounds

    def is_over(self) -> bool:
        """Whether the game has ended. Checked after each set of operating rounds.

        Standard rules: after ``total_rounds``. Death Star rules: after the set of operating
        rounds in which the station launched, or after ``death_star_backstop_rounds``.
        """
        return self.round_number >= self.round_limit()


def _seizure_choice(owned: list[Facility], site: Hex) -> tuple[Facility, bool]:
    """The facility of ``owned`` (not empty) that a seizure takes: the one nearest ``site``,
    the most recently built on a tie. The flag says whether the nearest lay on more than one
    planet, so the tie-break decided which planet."""
    nearest = min(f.planet.distance(site) for f in owned)
    closest = [f for f in owned if f.planet.distance(site) == nearest]
    taken = max(closest, key=lambda f: f.build_number)
    return taken, len({f.planet for f in closest}) > 1
