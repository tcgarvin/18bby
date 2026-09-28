"""A one-step greedy bot: builds toward revenue, buys into the best-earning corporations."""

from __future__ import annotations

import random

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
from bby18.game import Game
from bby18.hexgrid import Hex
from bby18.revenue import compute_revenue
from bby18.state import Corporation, CorpStatus, Player


class GreedyBot:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    # --- stock round ---------------------------------------------------------

    def choose_stock_action(
        self, game: Game, player: Player, legal: list[StockAction]
    ) -> StockAction:
        buys = [a for a in legal if isinstance(a, BuyShare)]
        if not buys:
            return PassStock()
        # Prefer buying into floated corporations by revenue per credit.
        scored: list[tuple[float, BuyShare]] = []
        for action in buys:
            corp = game.corp(action.corp_id)
            if corp.status is CorpStatus.UNSTARTED:
                # Only start a corporation if this player presides over none, at the lowest par.
                presides = any(c.president == player.id for c in game.corporations.values())
                if presides or action.par != min(game.config.par_prices):
                    continue
                scored.append((1.0, action))
                continue
            cost = corp.par if action.source is ShareSource.IPO else game.price(corp)
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

    # --- operating round -----------------------------------------------------

    def choose_network_action(
        self, game: Game, corp: Corporation, legal: list[NetworkAction]
    ) -> NetworkAction:
        candidates = [a for a in legal if not isinstance(a, NoNetworkAction)]
        if not candidates:
            return NoNetworkAction()
        current = game.revenue(corp).total
        unreached = [p for p in game.board.planets if p.hex not in game.reachable(corp)]
        best: tuple[float, NetworkAction] | None = None
        for action in candidates:
            gain = self._revenue_after(game, corp, action) - current
            if isinstance(action, (Chart, ExtendService)):
                position: Hex = action.hex
            else:
                position = action.hex.neighbor(action.new_exit)
            distance = min((p.hex.distance(position) for p in unreached), default=0)
            score = gain * 100 - distance * 10 - action.cost / 10 + self.rng.random()
            if best is None or score > best[0]:
                best = (score, action)
        assert best is not None
        if best[0] < -50 and corp.treasury < game.config.chart_cost * 2:
            return NoNetworkAction()
        return best[1]

    def _revenue_after(self, game: Game, corp: Corporation, action: NetworkAction) -> int:
        net = game.network.copy()
        reach = net.reachable(corp.id, game.homeworld(corp))
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
        return corp.treasury >= game.config.chart_cost * 2
