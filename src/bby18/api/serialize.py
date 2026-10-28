"""JSON-friendly views of board, game state and actions.

Actions round-trip: ``action_to_json`` produces a dict, and ``match_action`` finds the legal
action whose JSON form equals a submitted dict. Clients never construct actions themselves;
they echo back one of the legal ones.

A state answering a request that played moves carries them as ``moves``: one frame per move,
built by a ``MoveRecorder`` observing the session, each with a compact view of the game just
after the move so clients can animate what opponents did.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType
from typing import Any

from bby18.actions import (
    BuildFacility,
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
from bby18.config import FleetTier, GameConfig, Unlimited
from bby18.death_star import SITE_NAME, STAGE_NAMES, DeathStarTrack
from bby18.game import BuyBlock, Game, LogEntry
from bby18.hexgrid import Direction, Hex
from bby18.network import Tile
from bby18.session import OPERATING_PHASES, Action, Dividend, GameSession, Phase, PlayedMove
from bby18.state import Corporation, Facility, Player

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
    if isinstance(action, BuildFacility):
        data = {"type": "build_facility", "planet": hex_to_json(action.planet), "cost": action.cost}
        # Like a buy's par, the exit is listed only when given: absent, it is left unclaimed.
        if action.exit_side is not None:
            data["exit"] = action.exit_side.name
        return data
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


def _fleet_revenue(game: Game, corp: Corporation) -> Json:
    """What a corporation's network would earn with one more fleet, and with no fleet limit at
    all, so a client can show what the next fleet adds and how many pairs go unrun."""
    if not corp.floated:
        return {"withNextFleet": 0, "uncapped": 0, "uncappedPairs": 0}
    planets = game.reachable_planets(corp)
    floor = game.config.homeworld_basic_income
    with_next = game.planet_revenue(planets, game.pair_cap(corp) + 1)
    uncapped = game.planet_revenue(planets)
    return {
        "withNextFleet": max(with_next.total, floor),
        "uncapped": max(uncapped.total, floor),
        "uncappedPairs": len(uncapped.pairs),
    }


def _corp_to_json(game: Game, corp_id: str) -> Json:
    corp = game.corp(corp_id)
    revenue = game.revenue(corp) if corp.floated else None
    data = {
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
                    {
                        "a": pair.a.name,
                        "b": pair.b.name,
                        "value": pair.value,
                        "typed": pair.typed,
                        "contract": pair.contract,
                    }
                    for pair in revenue.pairs
                ],
            }
            if revenue is not None
            else {"total": 0, "pairs": []}
        ),
    }
    if game.config.death_star_rules:
        data["fleetRevenue"] = _fleet_revenue(game, corp)
    return data


def _site_status(track: DeathStarTrack, index: int) -> str:
    """``active`` (under construction), ``reserved`` (a future site), ``vacated`` (the site
    moved on and the hex is empty space), ``launched`` (the station left from here and the hex
    is empty space) or ``unused`` (a future site the station launched before reaching)."""
    if index < track.site_index:
        return "vacated"
    if index == track.site_index:
        return "launched" if track.launched else "active"
    return "unused" if track.launched else "reserved"


def stage_title(index: int) -> str:
    """A stage's display name; ``index`` is 0-based."""
    return STAGE_NAMES[index] if index < len(STAGE_NAMES) else f"Stage {index + 1}"


def _count_json(count: int | Unlimited) -> int | str:
    return count.value if isinstance(count, Unlimited) else count


def fleet_tiers_to_json(tiers: tuple[FleetTier, ...], sold: int) -> list[Json]:
    """Each tier's price, size and fleets left after ``sold`` have been sold. An unlimited
    tier's count and remaining are the string ``"unlimited"``."""
    result: list[Json] = []
    left_to_place = sold
    for tier in tiers:
        if isinstance(tier.count, Unlimited):
            remaining: int | str = tier.count.value
        else:
            taken = min(left_to_place, tier.count)
            left_to_place -= taken
            remaining = tier.count - taken
        result.append(
            {"price": tier.price, "count": _count_json(tier.count), "remaining": remaining}
        )
    return result


def death_star_to_json(game: Game) -> Json:
    """The Death Star track, its construction sites and the fleet (or facility) supply (Death
    Star rules only)."""
    config = game.config
    track = game.death_star
    filled = track.stages_filled(config)
    # Regions as on the map: a space hex takes its nearest real planet's region, not the site's.
    base = game.board.without_planet(SITE_NAME) if track.active_site is not None else game.board
    tiers = fleet_tiers_to_json(config.fleet_tiers, game.fleets_sold)
    tier = game.fleet_tier()
    return {
        "siteName": SITE_NAME,
        "siteTag": config.death_star_tag,
        "contractPartnerTags": sorted(config.contract_partner_tags),
        "sites": [
            {
                "hex": hex_to_json(h),
                "region": base.region_of(h),
                "status": _site_status(track, i),
            }
            for i, h in enumerate(track.sites)
        ],
        "cubes": track.cubes,
        "cubesPerStage": config.death_star_cubes_per_stage,
        "totalCubes": config.death_star_cubes_per_stage * len(config.death_star_stage_values),
        "stages": [
            {
                "name": stage_title(i),
                "value": value,
                "result": result,
                "filled": i < filled,
                "resolved": i < track.stages_resolved,
            }
            for i, (value, result) in enumerate(
                zip(config.death_star_stage_values, config.death_star_stage_results)
            )
        ],
        "stage": game.death_star_stage(),
        "contractValue": game.contract_value(),
        "launched": track.launched,
        "finalRound": game.round_limit(),
        "backstopRound": config.death_star_backstop_rounds,
        "empireCubesPerStockRound": config.empire_cubes_per_stock_round,
        "fleets": {
            # The facility rules sell facilities from the same supply, at the same tiers.
            "item": "facility" if config.facility_rules else "fleet",
            "price": game.fleet_price(),
            "tier": tier,
            "remainingInTier": tiers[tier]["remaining"],
            "tiers": tiers,
            "limit": config.fleet_limit,
            "sold": game.fleets_sold,
        },
    }


def facility_json(facility: Facility) -> Json:
    """One facility: its owner (a corporation id, or ``"Empire"`` once seized) and when it was
    built, from 0 for the game's first."""
    return {"owner": facility.owner, "build": facility.build_number}


def planet_exits_map(game: Game) -> dict[Hex, Json]:
    """Every exit-limited planet's exits and facilities, keyed by hex (facility rules only;
    the construction site keeps every exit and is not listed). ``claimed`` are the sides it
    connects through, ``dangling`` the sides where a lane faces it without an exit, and
    ``freeSlots`` the facilities a floated corporation may still build there."""
    network = game.network
    planets: dict[Hex, Json] = {}
    for planet in game.board.planets:
        hex = planet.hex
        if not network.has_exit_limit(hex):
            continue
        planets[hex] = {
            "hex": hex_to_json(hex),
            "name": planet.name,
            "exits": network.planet_exits(hex),
            "claimed": [d.name for d in sorted(network.claimed_exits(hex))],
            "unclaimed": network.unclaimed_exits(hex),
            "dangling": [d.name for d in sorted(network.dangling_sides(hex))],
            "facilities": [facility_json(f) for f in game.facilities_on(hex)],
            "freeSlots": game.free_facility_slots(hex),
        }
    return dict(sorted(planets.items()))


def facilities_to_json(game: Game, planets: Iterable[Json]) -> Json:
    """The facility rules' state with ``planets`` (from ``planet_exits_map``: all of them, or a
    move frame's changed ones), and the facility the next seizure would take from each
    corporation that owns one."""
    return {
        "perPlanet": game.config.facilities_per_planet,
        "planets": list(planets),
        "seizureTargets": [
            {"corp": corp_id, "hex": hex_to_json(f.planet)}
            for corp_id, f in game.facilities_to_seize().items()
        ],
    }


def _facility_options(session: GameSession) -> list[Json]:
    """For each facility the operating corporation may build now, what its network would earn
    with it (one more pair, and the lane the new exit is given to), the planets that lane would
    newly reach, and whose lane it is. Empty outside a facility step."""
    if session.phase is not Phase.FLEET:
        return []
    game = session.game
    corp = session.current_corporation
    home = game.homeworld(corp)
    before = game.reachable(corp)
    floor = game.config.homeworld_basic_income
    options: list[Json] = []
    for action in session.legal_actions():
        if not isinstance(action, BuildFacility):
            continue
        network = game.network_after_facility(action)
        reach = network.reachable(corp.id, home)
        planets = [game.board.planet_at(h) for h in sorted(reach) if game.board.is_planet(h)]
        revenue = game.planet_revenue(planets, game.pair_cap(corp) + 1)
        lane = (
            sorted(network.corporations_serving(action.planet.neighbor(action.exit_side)))
            if action.exit_side is not None
            else []
        )
        options.append(
            {
                "action": action_to_json(action),
                "revenue": max(revenue.total, floor),
                "reaches": [
                    game.board.planet_at(h).name
                    for h in sorted(reach - before)
                    if game.board.is_planet(h)
                ],
                "lane": lane,
            }
        )
    return options


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


def buy_blocks_to_json(session: GameSession) -> Json:
    """Why the current player cannot buy each corporation they cannot, for the stock round's
    corporation cards; a blocked purchase they lack the cash for also gives its cost."""
    game = session.game
    data: Json = {}
    for corp_id, block in session.buy_blocks().items():
        entry: Json = {"reason": block.value}
        if block is BuyBlock.CANNOT_AFFORD:
            entry["cost"] = game.cheapest_buy_cost(game.corp(corp_id))
        data[corp_id] = entry
    return data


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
    data = {
        **_turn_to_json(session),
        "totalRounds": game.round_limit(),
        "waitingOnHuman": session.waiting_on_human(),
        "legalActions": [action_to_json(a) for a in session.legal_actions()],
        "buyBlocks": buy_blocks_to_json(session),
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
    if game.config.death_star_rules:
        data["deathStar"] = death_star_to_json(game)
    if game.config.facility_rules:
        data["facilities"] = {
            **facilities_to_json(game, planet_exits_map(game).values()),
            "options": _facility_options(session),
        }
    return data


NOTHING_BEFORE: Mapping[Hex, Json] = MappingProxyType({})
"""No map state known before the first observed move."""


class MoveRecorder:
    """A session observer that turns each move into a ``MoveFrame`` (see web/src/api.ts).

    Pass it to ``GameSession.apply`` or ``run_bots``; read ``frames`` afterwards. Each frame's
    ``after.tiles`` lists only the tiles the move changed, found by comparing with the tiles
    as they stood after the previous move (or ``tiles_before`` for the first). Under the
    facility rules ``after.facilities.planets`` likewise lists only the planets whose exits or
    facilities the move changed.
    """

    def __init__(
        self, tiles_before: Mapping[Hex, Json], planets_before: Mapping[Hex, Json] = NOTHING_BEFORE
    ) -> None:
        """``tiles_before``: the board's tiles before the first observed move, as
        ``tile_map`` gives them; empty for a new game. ``planets_before``: likewise the
        exit-limited planets, as ``planet_exits_map`` gives them; when empty, the first frame
        lists every one."""
        self._tiles: dict[Hex, Json] = dict(tiles_before)
        self._planets: dict[Hex, Json] = dict(planets_before)
        self.frames: list[Json] = []

    def __call__(self, session: GameSession, move: PlayedMove) -> None:
        game = session.game
        tiles = tile_map(game)
        changed = [tile for h, tile in tiles.items() if self._tiles.get(h) != tile]
        self._tiles = tiles
        after: Json = {
            **_turn_to_json(session),
            "players": [player_to_json(game, p) for p in game.players],
            "corporations": [_corp_to_json(game, c) for c in game.corporations],
            "tiles": changed,
        }
        if game.config.death_star_rules:
            after["deathStar"] = death_star_to_json(game)
        if game.config.facility_rules:
            planets = planet_exits_map(game)
            moved = [p for h, p in planets.items() if self._planets.get(h) != p]
            self._planets = planets
            after["facilities"] = facilities_to_json(game, moved)
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
                "after": after,
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
        "deathStarRules": config.death_star_rules,
        "deathStar": death_star_rules_to_json(config),
        "facilityRules": config.facility_rules,
        "facilities": facility_rules_to_json(config),
    }


def facility_rules_to_json(config: GameConfig) -> Json:
    """The facility numbers. Always listed; ``facilityRules`` in ``rules_to_json``
    says whether they are in force. Facilities are priced by the fleet tiers and limited by the
    fleet limit, listed under ``deathStar``."""
    return {
        "perPlanet": config.facilities_per_planet,
        "baseExits": config.planet_base_exits,
    }


def death_star_rules_to_json(config: GameConfig) -> Json:
    """The Death Star and fleet numbers. Always listed; ``deathStarRules`` in
    ``rules_to_json`` says whether they are in force."""
    return {
        "fleetTiers": fleet_tiers_to_json(config.fleet_tiers, 0),
        "fleetLimit": config.fleet_limit,
        "siteTag": config.death_star_tag,
        "contractPartnerTags": sorted(config.contract_partner_tags),
        "stages": [
            {"name": stage_title(i), "value": value, "result": result}
            for i, (value, result) in enumerate(
                zip(config.death_star_stage_values, config.death_star_stage_results)
            )
        ],
        "cubesPerStage": config.death_star_cubes_per_stage,
        "empireCubesPerStockRound": config.empire_cubes_per_stock_round,
        "backstopRounds": config.death_star_backstop_rounds,
        "siteRegions": list(config.death_star_site_regions),
        "minHomeworldDistance": config.death_star_min_homeworld_distance,
    }


DIRECTION_NAMES = [d.name for d in Direction]
