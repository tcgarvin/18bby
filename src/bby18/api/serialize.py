"""JSON-friendly views of board, game state and actions.

Actions round-trip: ``action_to_json`` produces a dict, and ``match_action`` finds the legal
action whose JSON form equals a submitted dict. Clients never construct actions themselves;
they echo back one of the legal ones.
"""

from __future__ import annotations

from typing import Any

from bby18.actions import (
    BuyShare,
    Chart,
    ExtendService,
    NoNetworkAction,
    PassStock,
    SellShares,
    Upgrade,
)
from bby18.board import Board
from bby18.game import Game
from bby18.hexgrid import Direction, Hex
from bby18.session import Action, Dividend, GameSession, Phase

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
    if isinstance(action, Dividend):
        return {"type": "dividend", "choice": action.value}
    raise TypeError(f"Cannot serialize {action!r}")


def match_action(legal: list[Action], submitted: Json) -> Action:
    """Find the legal action whose JSON form equals ``submitted``."""
    for action in legal:
        if action_to_json(action) == submitted:
            return action
    raise ValueError(f"Submitted action {submitted!r} is not legal right now")


def _corp_to_json(game: Game, corp_id: str) -> Json:
    corp = game.corp(corp_id)
    revenue = game.revenue(corp) if corp.floated else None
    return {
        "id": corp.id,
        "name": corp.spec.name,
        "homeworld": corp.spec.homeworld,
        "status": corp.status.value,
        "par": corp.par,
        "price": game.price(corp) if corp.status.value != "unstarted" else 0,
        "treasury": corp.treasury,
        "ipoShares": corp.ipo_shares,
        "poolShares": corp.pool_shares,
        "president": corp.president,
        "lastRevenue": corp.last_revenue,
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


def session_to_json(session: GameSession) -> Json:
    game = session.game
    over = session.phase is Phase.GAME_OVER
    tiles = [
        {
            "hex": hex_to_json(h),
            "exits": [d.name for d in sorted(t.exits)],
            "service": sorted(game.network.corporations_serving(h)),
        }
        for h, t in sorted(game.network.tiles().items())
    ]
    return {
        "phase": session.phase.value,
        "roundLabel": game.round_label,
        "roundNumber": game.round_number,
        "totalRounds": game.config.total_rounds,
        "currentPlayer": None if over else session.current_player.id,
        "currentCorporation": (
            session.current_corporation.id
            if session.phase in (Phase.NETWORK, Phase.DIVIDEND)
            else None
        ),
        "waitingOnHuman": session.waiting_on_human(),
        "legalActions": [action_to_json(a) for a in session.legal_actions()],
        "players": [
            {
                "id": p.id,
                "name": p.name,
                "cash": p.cash,
                "worth": game.player_worth(p),
                "shares": {c: n for c, n in p.shares.items() if n},
                "isBot": p.id in session.bots,
                "certificates": game.certificate_count(p),
            }
            for p in game.players
        ],
        "priorityPlayer": game.players[game.priority_player].id,
        "corporations": [_corp_to_json(game, c) for c in game.corporations],
        "operatingOrder": [c.id for c in game.operating_order()],
        "tiles": tiles,
        "stockTrack": list(game.config.stock_track),
        "config": {
            "chartCost": game.config.chart_cost,
            "upgradeCost": game.config.upgrade_cost,
            "serviceCost": game.config.service_cost,
            "parPrices": list(game.config.par_prices),
            "sharesPerCorporation": game.config.shares_per_corporation,
            "certificateLimit": game.config.certificate_limit,
            "maxHoldingShares": game.config.max_holding_shares,
            "typedPairValue": game.config.typed_pair_value,
            "regionalBonus": game.config.regional_bonus,
            "basicRouteValue": game.config.basic_route_value,
        },
        "log": [
            {"seq": i, "round": e.round_label, "actor": e.actor, "text": e.text}
            for i, e in enumerate(game.log)
        ][-200:],
    }


DIRECTION_NAMES = [d.name for d in Direction]
