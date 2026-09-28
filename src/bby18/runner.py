"""Run a whole game with a decider for every seat."""

from __future__ import annotations

from bby18.game import Game
from bby18.session import Decider, GameSession

__all__ = ["Decider", "run_game"]


def run_game(game: Game, deciders: dict[str, Decider]) -> Game:
    if set(deciders) != {p.id for p in game.players}:
        raise ValueError("A decider is required for every player")
    session = GameSession(game, bots=deciders)
    session.run_bots()
    return game
