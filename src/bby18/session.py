"""A step-driven game controller.

``GameSession`` turns the game into a state machine: at any moment there is one phase, one
actor, and a list of legal actions. Callers (a web API, a CLI, the bot runner) apply one
action at a time. Seats occupied by bots are played automatically after each step.

Two options serve interactive clients: ``auto_forced`` plays any move that is the only legal
one, so a human never has to click through it, and ``record_undo`` keeps a snapshot before
every submitted action so ``undo`` can take it back.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from bby18.actions import NetworkAction, NoNetworkAction, PassStock, StockAction
from bby18.game import Game
from bby18.state import Corporation, Player


class Decider(Protocol):
    """Anything that can make decisions for a seat: a bot, a scripted test, a human proxy."""

    def choose_stock_action(
        self, game: Game, player: Player, legal: list[StockAction]
    ) -> StockAction: ...

    def choose_network_action(
        self, game: Game, corp: Corporation, legal: list[NetworkAction]
    ) -> NetworkAction: ...

    def choose_pay_dividends(self, game: Game, corp: Corporation, revenue: int) -> bool: ...


class Phase(Enum):
    STOCK = "stock"
    NETWORK = "network"
    DIVIDEND = "dividend"
    GAME_OVER = "game_over"


class Dividend(Enum):
    PAY = "pay"
    WITHHOLD = "withhold"


Action = StockAction | NetworkAction | Dividend


@dataclass
class _StockState:
    current: int
    consecutive_passes: int = 0
    sold: dict[str, set[str]] = field(default_factory=dict)


@dataclass
class _OperatingState:
    index: int
    queue: list[str]
    position: int = 0
    actions_taken: int = 0


class GameSession:
    def __init__(
        self,
        game: Game,
        bots: dict[str, Decider] | None = None,
        *,
        auto_forced: bool = False,
        record_undo: bool = False,
    ) -> None:
        self.game = game
        self.bots: dict[str, Decider] = dict(bots or {})
        self.auto_forced = auto_forced
        self.record_undo = record_undo
        self.automatic_log_start = 0
        """Log entries from this index on were played automatically (by bots or as forced
        moves) after the last submitted action."""
        self._history: list[dict[str, Any]] = []
        self.phase = Phase.STOCK
        self._stock = _StockState(current=game.priority_player)
        self._operating = _OperatingState(index=0, queue=[])
        self._begin_stock_round()

    # --- public queries --------------------------------------------------------

    @property
    def current_player(self) -> Player:
        """The player who must act now. Raises when the game is over."""
        if self.phase is Phase.STOCK:
            return self.game.players[self._stock.current]
        if self.phase in (Phase.NETWORK, Phase.DIVIDEND):
            return self.game.player(self.current_corporation.president)
        raise ValueError("The game is over; nobody acts")

    @property
    def current_corporation(self) -> Corporation:
        if self.phase not in (Phase.NETWORK, Phase.DIVIDEND):
            raise ValueError(f"No corporation acts during {self.phase.value}")
        return self.game.corp(self._operating.queue[self._operating.position])

    def legal_actions(self) -> list[Action]:
        if self.phase is Phase.STOCK:
            player = self.current_player
            return list(self.game.legal_stock_actions(player, self._stock.sold[player.id]))
        if self.phase is Phase.NETWORK:
            return list(self.game.legal_network_actions(self.current_corporation))
        if self.phase is Phase.DIVIDEND:
            if self.game.revenue(self.current_corporation).total == 0:
                return [Dividend.WITHHOLD]
            return [Dividend.PAY, Dividend.WITHHOLD]
        return []

    @property
    def network_actions_taken(self) -> int:
        """Network actions the operating corporation has taken this turn."""
        return self._operating.actions_taken

    def waiting_on_human(self) -> bool:
        return self.phase is not Phase.GAME_OVER and self.current_player.id not in self.bots

    # --- stepping --------------------------------------------------------------

    @property
    def can_undo(self) -> bool:
        return bool(self._history)

    def apply(self, action: Action) -> None:
        """Apply one action for the current actor, then play on any automatic moves."""
        snapshot = self._snapshot() if self.record_undo else None
        self._apply_one(action)
        if snapshot is not None:
            self._history.append(snapshot)
        self.automatic_log_start = len(self.game.log)
        self.run_bots()

    def undo(self) -> None:
        """Restore the game to just before the last submitted action.

        Moves that bots or forced choices made after it are taken back too. Requires
        ``record_undo``; raises ValueError when there is nothing to undo.
        """
        if not self._history:
            raise ValueError("Nothing to undo")
        history = self._history
        vars(self).update(history.pop())
        self._history = history

    def run_bots(self) -> None:
        """Play moves that need no human: bot seats, and forced moves if ``auto_forced``."""
        while (action := self._automatic_action()) is not None:
            self._apply_one(action)

    def _automatic_action(self) -> Action | None:
        if self.phase is Phase.GAME_OVER:
            return None
        if self.current_player.id in self.bots:
            return self._bot_choice()
        if self.auto_forced:
            legal = self.legal_actions()
            if len(legal) == 1:
                return legal[0]
        return None

    def _snapshot(self) -> dict[str, Any]:
        # One deepcopy call keeps references shared between fields (such as game and bots) intact.
        state = {key: value for key, value in vars(self).items() if key != "_history"}
        return copy.deepcopy(state)

    def _bot_choice(self) -> Action:
        bot = self.bots[self.current_player.id]
        legal = self.legal_actions()
        if self.phase is Phase.STOCK:
            stock_legal = [a for a in legal if not isinstance(a, Dividend)]
            return bot.choose_stock_action(self.game, self.current_player, stock_legal)  # type: ignore[arg-type]
        corp = self.current_corporation
        if self.phase is Phase.NETWORK:
            net_legal = [a for a in legal if not isinstance(a, Dividend)]
            return bot.choose_network_action(self.game, corp, net_legal)  # type: ignore[arg-type]
        revenue = self.game.revenue(corp).total
        if revenue == 0:
            return Dividend.WITHHOLD
        return (
            Dividend.PAY
            if bot.choose_pay_dividends(self.game, corp, revenue)
            else Dividend.WITHHOLD
        )

    def _apply_one(self, action: Action) -> None:
        legal = self.legal_actions()
        if action not in legal:
            raise ValueError(f"{action!r} is not legal in phase {self.phase.value}")
        if self.phase is Phase.STOCK:
            self._stock_step(action)  # type: ignore[arg-type]
        elif self.phase is Phase.NETWORK:
            self._network_step(action)  # type: ignore[arg-type]
        elif self.phase is Phase.DIVIDEND:
            self._dividend_step(action)  # type: ignore[arg-type]
        else:
            raise ValueError("The game is over")

    # --- stock round -----------------------------------------------------------

    def _begin_stock_round(self) -> None:
        game = self.game
        game.round_label = f"SR{game.round_number + 1}"
        self.phase = Phase.STOCK
        self._stock = _StockState(
            current=game.priority_player, sold={p.id: set() for p in game.players}
        )

    def _stock_step(self, action: StockAction) -> None:
        game = self.game
        n = len(game.players)
        player = game.players[self._stock.current]
        game.apply_stock_action(player, action, self._stock.sold[player.id])
        if isinstance(action, PassStock):
            self._stock.consecutive_passes += 1
        else:
            self._stock.consecutive_passes = 0
            game.priority_player = (self._stock.current + 1) % n
        self._stock.current = (self._stock.current + 1) % n
        if self._stock.consecutive_passes >= n:
            game.finish_stock_round()
            self._begin_operating_round(0)

    # --- operating rounds ------------------------------------------------------

    def _begin_operating_round(self, index: int) -> None:
        game = self.game
        if index >= game.config.operating_rounds_per_stock_round:
            game.round_number += 1
            if game.is_over():
                game.round_label = "end"
                self.phase = Phase.GAME_OVER
            else:
                self._begin_stock_round()
            return
        game.round_label = f"OR{game.round_number + 1}.{index + 1}"
        queue = [c.id for c in game.operating_order()]
        self._operating = _OperatingState(index=index, queue=queue)
        if not queue:
            self._begin_operating_round(index + 1)
            return
        self.phase = Phase.NETWORK

    def _network_step(self, action: NetworkAction) -> None:
        self.game.apply_network_action(self.current_corporation, action)
        self._operating.actions_taken += 1
        # Passing ends the corporation's network actions for this turn.
        done = isinstance(action, NoNetworkAction)
        if done or self._operating.actions_taken >= self.game.config.network_actions_per_turn:
            self.phase = Phase.DIVIDEND

    def _dividend_step(self, action: Dividend) -> None:
        self.game.settle_revenue(self.current_corporation, pay=action is Dividend.PAY)
        self._operating.position += 1
        self._operating.actions_taken = 0
        if self._operating.position >= len(self._operating.queue):
            self._begin_operating_round(self._operating.index + 1)
        else:
            self.phase = Phase.NETWORK
