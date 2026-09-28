"""Drives a game through stock and operating rounds using a decision-maker per player."""

from __future__ import annotations

from typing import Protocol

from bby18.actions import NetworkAction, PassStock, StockAction
from bby18.game import Game
from bby18.state import Corporation, Player


class Decider(Protocol):
    """Anything that can make decisions for a player: a bot, a human UI, a script."""

    def choose_stock_action(
        self, game: Game, player: Player, legal: list[StockAction]
    ) -> StockAction: ...

    def choose_network_action(
        self, game: Game, corp: Corporation, legal: list[NetworkAction]
    ) -> NetworkAction: ...

    def choose_pay_dividends(self, game: Game, corp: Corporation, revenue: int) -> bool: ...


def run_stock_round(game: Game, deciders: dict[str, Decider]) -> None:
    game.round_label = f"SR{game.round_number + 1}"
    sold_this_round: dict[str, set[str]] = {p.id: set() for p in game.players}
    n = len(game.players)
    current = game.priority_player
    consecutive_passes = 0
    while consecutive_passes < n:
        player = game.players[current]
        legal = game.legal_stock_actions(player, sold_this_round[player.id])
        action = deciders[player.id].choose_stock_action(game, player, legal)
        if action not in legal:
            raise ValueError(f"{player.name} chose illegal stock action {action!r}")
        game.apply_stock_action(player, action, sold_this_round[player.id])
        if isinstance(action, PassStock):
            consecutive_passes += 1
        else:
            consecutive_passes = 0
            game.priority_player = (current + 1) % n
        current = (current + 1) % n
    game.stock_rounds_played += 1


def run_operating_round(game: Game, deciders: dict[str, Decider], index: int) -> None:
    game.round_label = f"OR{game.round_number + 1}.{index + 1}"
    for corp in game.operating_order():
        decider = deciders[corp.president]
        for _ in range(game.config.network_actions_per_turn):
            legal = game.legal_network_actions(corp)
            action = decider.choose_network_action(game, corp, legal)
            if action not in legal:
                raise ValueError(f"{corp.id} chose illegal network action {action!r}")
            game.apply_network_action(corp, action)
        revenue = game.revenue(corp).total
        pay = decider.choose_pay_dividends(game, corp, revenue)
        game.settle_revenue(corp, pay)


def run_game(game: Game, deciders: dict[str, Decider]) -> Game:
    while not game.is_over():
        run_stock_round(game, deciders)
        for i in range(game.config.operating_rounds_per_stock_round):
            run_operating_round(game, deciders, i)
        game.round_number += 1
    game.round_label = "end"
    return game
