"""JSON-friendly views of board, game state and actions.

Actions round-trip: ``action_to_json`` produces a dict, and ``match_action`` finds the legal
action whose JSON form equals a submitted dict. Clients never construct actions themselves;
they echo back one of the legal ones.

A state answering a request that played moves carries them as ``moves``: one frame per move,
built by a ``MoveRecorder`` observing the session, each with a compact view of the game just
after the move so clients can animate what opponents did.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from bby18.actions import (
    BuyFleet,
    BuyShare,
    Chart,
    ExtendService,
    FinishFleets,
    NoNetworkAction,
    PassStock,
    SellShares,
    Upgrade,
)
from bby18.board import Board
from bby18.config import GameConfig
from bby18.game import Game, LogEntry
from bby18.hexgrid import Direction, Hex
from bby18.network import Tile
from bby18.session import OPERATING_PHASES, Action, Dividend, GameSession, Phase, PlayedMove
from bby18.state import Corporation, Player

Json = dict[str, Any]


def hex_to_json(hex: Hex) -> list[int]:
    return [hex.q, hex.r]


def board_to_json(board: Board) -> Json:
    return {
        "radius": board.radius,
        "hexes": [hex_to_json(h) for h in sorted(board.hexes)],
        "planets": [
            {
                "name": p.name,
                "hex": hex_to_json(p.hex),
                "region": p.region,
                "tags": sorted(p.tags),
            }
            for p in board.planets
        ],
    }


def action_to_json(action: Action) -> Json:
    if isinstance(action, PassStock):
        return {"type": "pass"}
    if isinstance(action, BuyShare):
        data: Json = {"type": "buy", "corp": action.corp_id, "source": action.source.value}
        if action.par:
            data["par"] = action.par
        return data
    if isinstance(action, SellShares):
        return {"type": "sell", "corp": action.corp_id, "count": action.count}
    if isinstance(action, Chart):
        return {
            "type": "chart",
            "hex": hex_to_json(action.hex),
            "exits": [d.name for d in sorted(action.exits)],
            "cost": action.cost,
        }
    if isinstance(action, Upgrade):
        return {
            "type": "upgrade",
            "hex": hex_to_json(action.hex),
            "exit": action.new_exit.name,
            "cost": action.cost,
        }
    if isinstance(action, ExtendService):
        return {"type": "service", "hex": hex_to_json(action.hex), "cost": action.cost}
    if isinstance(action, NoNetworkAction):
        return {"type": "no_action"}
    if isinstance(action, BuyFleet):
        return {"type": "buy_fleet", "cost": action.cost}
    if isinstance(action, FinishFleets):
        return {"type": "finish_fleets"}
    if isinstance(action, Dividend):
        return {"type": "dividend", "choice": action.value}
    raise TypeError(f"Cannot serialize {action!r}")


def match_action(legal: list[Action], submitted: Json) -> Action:
    """Find the legal action whose JSON form equals ``submitted``."""
    for action in legal:
        if action_to_json(action) == submitted:
            return action
    raise ValueError(f"Submitted action {submitted!r} is not legal right now")


def _dividend_preview(game: Game, corp: Corporation, revenue: int) -> Json | None:
    """Share price after paying or withholding this revenue, for the dividend buttons."""
    if not corp.floated:
        return None
    market = game.market
    steps = game.payout_steps(revenue, game.price(corp))
    withheld = (
        market.left(corp.market_cell)
        if revenue > 0 or game.config.zero_revenue_moves_price
        else corp.market_cell
    )
    paid = market.right(corp.market_cell, steps) if revenue > 0 else withheld
    return {
        "pay": market.price_at(paid),
        "withhold": market.price_at(withheld),
    }


def _corp_to_json(game: Game, corp_id: str) -> Json:
    corp = game.corp(corp_id)
    revenue = game.revenue(corp) if corp.floated else None
    return {
        "id": corp.id,
        "name": corp.spec.name,
        "homeworld": corp.spec.homeworld,
        "status": corp.status.value,
        "par": corp.par,
        "ipoPrice": game.ipo_price(corp),
        "price": game.price(corp) if corp.status.value != "unstarted" else 0,
        "marketCell": (
            [corp.market_cell.row, corp.market_cell.col]
            if corp.status.value != "unstarted"
            else None
        ),
        "dividendPreview": _dividend_preview(game, corp, revenue.total if revenue else 0),
        "treasury": corp.treasury,
        "ipoShares": corp.ipo_shares,
        "poolShares": corp.pool_shares,
        "president": corp.president,
        "lastRevenue": corp.last_revenue,
        "fleets": corp.fleets,
        "reachablePlanets": [p.name for p in game.reachable_planets(corp)] if corp.floated else [],
        "revenue": (
            {
                "total": revenue.total,
                "pairs": [
                    {"a": pair.a.name, "b": pair.b.name, "value": pair.value, "typed": pair.typed}
                    for pair in revenue.pairs
                ],
            }
            if revenue is not None
            else {"total": 0, "pairs": []}
        ),
    }


def tile_to_json(game: Game, hex: Hex, tile: Tile) -> Json:
    """A charted tile: its exits and the corporations with service on it."""
    return {
        "hex": hex_to_json(hex),
        "exits": [d.name for d in sorted(tile.exits)],
        "service": sorted(game.network.corporations_serving(hex)),
    }


def tile_map(game: Game) -> dict[Hex, Json]:
    """Every charted tile's JSON, keyed by hex."""
    return {h: tile_to_json(game, h, t) for h, t in sorted(game.network.tiles().items())}


def player_to_json(game: Game, player: Player) -> Json:
    """A player's holdings; the parts of a player view that moves can change."""
    return {
        "id": player.id,
        "cash": player.cash,
        "worth": game.player_worth(player),
        "shares": {c: n for c, n in player.shares.items() if n},
        "certificates": game.certificate_count(player),
    }


def log_entry_to_json(seq: int, entry: LogEntry) -> Json:
    """A log line; ``seq`` is its index in the whole game log."""
    return {"seq": seq, "round": entry.round_label, "actor": entry.actor, "text": entry.text}


def _turn_to_json(session: GameSession) -> Json:
    """Whose turn it is and where the game stands, shared by full states and move frames."""
    game = session.game
    over = session.phase is Phase.GAME_OVER
    return {
        "phase": session.phase.value,
        "roundLabel": game.round_label,
        "roundNumber": game.round_number,
        "currentPlayer": None if over else session.current_player.id,
        "currentCorporation": (
            session.current_corporation.id if session.phase in OPERATING_PHASES else None
        ),
        "priorityPlayer": game.players[game.priority_player].id,
        "operatingOrder": session.operating_queue,
        "networkActionsTaken": session.network_actions_taken,
    }


def session_to_json(session: GameSession, moves: Sequence[Json] = ()) -> Json:
    """The full game state a client renders. ``moves`` are the frames of the moves the
    current request played (see ``MoveRecorder``); empty when it played none."""
    game = session.game
    return {
        **_turn_to_json(session),
        "totalRounds": game.round_limit(),
        "waitingOnHuman": session.waiting_on_human(),
        "legalActions": [action_to_json(a) for a in session.legal_actions()],
        "players": [
            {**player_to_json(game, p), "name": p.name, "isBot": p.id in session.bots}
            for p in game.players
        ],
        "corporations": [_corp_to_json(game, c) for c in game.corporations],
        "tiles": list(tile_map(game).values()),
        "terrain": [
            {"hex": hex_to_json(h), "kind": kind.value}
            for h, kind in sorted(game.board.terrain.items())
        ],
        "stockMarket": [list(row) for row in game.config.stock_market],
        "parColumn": game.config.par_column,
        "canUndo": session.can_undo,
        "automaticLogStart": session.automatic_log_start,
        "config": {
            "chartCost": game.config.chart_cost,
            "upgradeCost": game.config.upgrade_cost,
            "serviceCost": game.config.service_cost,
            "nebulaChartSurcharge": game.config.nebula_chart_surcharge,
            "networkActionsPerTurn": game.config.network_actions_per_turn,
            "parPrices": list(game.config.par_prices),
            "sharesPerCorporation": game.config.shares_per_corporation,
            "certificateLimit": game.config.certificate_limit,
            "maxHoldingShares": game.config.max_holding_shares,
            "typedPairValue": game.config.typed_pair_value,
            "regionalBonus": game.config.regional_bonus,
            "basicRouteValue": game.config.basic_route_value,
        },
        "log": [log_entry_to_json(i, e) for i, e in enumerate(game.log)][-200:],
        "moves": list(moves),
    }


class MoveRecorder:
    """A session observer that turns each move into a ``MoveFrame`` (see web/src/api.ts).

    Pass it to ``GameSession.apply`` or ``run_bots``; read ``frames`` afterwards. Each frame's
    ``after.tiles`` lists only the tiles the move changed, found by comparing with the tiles
    as they stood after the previous move (or ``tiles_before`` for the first).
    """

    def __init__(self, tiles_before: Mapping[Hex, Json]) -> None:
        """``tiles_before``: the board's tiles before the first observed move, as
        ``tile_map`` gives them; empty for a new game."""
        self._tiles: dict[Hex, Json] = dict(tiles_before)
        self.frames: list[Json] = []

    def __call__(self, session: GameSession, move: PlayedMove) -> None:
        game = session.game
        tiles = tile_map(game)
        changed = [tile for h, tile in tiles.items() if self._tiles.get(h) != tile]
        self._tiles = tiles
        self.frames.append(
            {
                "phase": move.phase.value,
                "roundLabel": move.round_label,
                "actor": move.actor,
                "corporation": move.corporation or None,
                "action": action_to_json(move.action),
                "automatic": move.automatic,
                "log": [
                    log_entry_to_json(i, game.log[i]) for i in range(move.log_start, len(game.log))
                ],
                "revenue": move.revenue,
                "after": {
                    **_turn_to_json(session),
                    "players": [player_to_json(game, p) for p in game.players],
                    "corporations": [_corp_to_json(game, c) for c in game.corporations],
                    "tiles": changed,
                },
            }
        )


def rules_to_json(config: GameConfig) -> Json:
    """Every number the rules page quotes, straight from the config so the docs cannot drift."""
    return {
        "corporations": [
            {"id": c.id, "name": c.name, "homeworld": c.homeworld} for c in config.corporations
        ],
        "networkActionsPerTurn": config.network_actions_per_turn,
        "chartCost": config.chart_cost,
        "upgradeCost": config.upgrade_cost,
        "serviceCost": config.service_cost,
        "nebulaChartSurcharge": config.nebula_chart_surcharge,
        "asteroidFraction": config.asteroid_fraction,
        "nebulaFraction": config.nebula_fraction,
        "typedPairValue": config.typed_pair_value,
        "typedPairs": sorted(sorted(pair) for pair in config.typed_pairs),
        "regionalBonus": config.regional_bonus,
        "regionalBonusRegions": sorted(config.regional_bonus_regions),
        "basicRouteValue": config.basic_route_value,
        "stockMarket": [list(row) for row in config.stock_market],
        "parColumn": config.par_column,
        "parPrices": list(config.par_prices),
        "payoutStepFractions": list(config.payout_step_fractions),
        "sharesPerCorporation": config.shares_per_corporation,
        "presidentShareSize": config.president_share_size,
        "floatThresholdShares": config.float_threshold_shares,
        "floatCapitalShares": config.float_capital_shares,
        "startingCash": {str(n): cash for n, cash in config.starting_cash_by_player_count.items()},
        "maxHoldingShares": config.max_holding_shares,
        "certificateLimit": config.certificate_limit,
        "totalRounds": config.total_rounds,
        "operatingRoundsPerStockRound": config.operating_rounds_per_stock_round,
    }


DIRECTION_NAMES = [d.name for d in Direction]
