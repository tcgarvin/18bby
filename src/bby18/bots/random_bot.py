"""A bot that acts uniformly at random. Useful as a baseline and a fuzzer."""

from __future__ import annotations

import random

from bby18.actions import NetworkAction, StockAction
from bby18.game import Game
from bby18.state import Corporation, Player


class RandomBot:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def choose_stock_action(
        self, game: Game, player: Player, legal: list[StockAction]
    ) -> StockAction:
        return self.rng.choice(legal)

    def choose_network_action(
        self, game: Game, corp: Corporation, legal: list[NetworkAction]
    ) -> NetworkAction:
        return self.rng.choice(legal)

    def choose_pay_dividends(self, game: Game, corp: Corporation, revenue: int) -> bool:
        return self.rng.random() < 0.5
