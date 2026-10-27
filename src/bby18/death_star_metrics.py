"""Per-game measurements of the Death Star rules, for balance sweeps.

``DeathStarRecorder`` is a session move observer: it watches every move as the game is played
and reads the structured state (the track, fleets, prices) before and after, so nothing is
recovered from log text. ``DeathStarRecorder.metrics`` turns what it saw into a
``DeathStarMetrics``, whose ``to_row`` gives the flat ``ds.*`` fields of a sweep row.

Times are on one **clock**: operating round ``r.i`` is ``(r - 1) * k + i`` with ``k`` operating
rounds per stock round, so it counts operating rounds from 1; stock round ``r`` sits just
before its operating rounds at ``(r - 1) * k + 0.5``. With two operating rounds per stock
round, SR1 is 0.5, OR1.1 is 1, OR1.2 is 2, SR2 is 2.5, and the eighth round's last OR is 16.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass

from bby18.actions import BuildFacility, BuyFleet, SellShares
from bby18.config import SEIZURE, SITE_MOVE, GameConfig
from bby18.facility_metrics import FacilityMetrics, build_exit_kind, facility_metrics
from bby18.game import Game
from bby18.session import Dividend, GameSession, Phase, PlayedMove
from bby18.state import CorpStatus

ROW_PREFIX = "ds."
"""Every Death Star row field starts with this; rows of games with the rules off have none."""

NEAR_SEIZURE_OPERATING_ROUNDS = 2
"""Dividend choices in this many operating rounds, up to and including the moment a seizure
stage fills, count as near the seizure."""

SALE_BEFORE_STAGE_RESULTS = (SEIZURE, SITE_MOVE)
"""Stages whose filling makes the stock round before it a "stock round before a stage"."""

_STOCK_LABEL = re.compile(r"^SR(\d+)$")
_OPERATING_LABEL = re.compile(r"^OR(\d+)\.(\d+)$")


@dataclass(frozen=True)
class RoundPoint:
    """Where a round label sits in the game."""

    round: int
    """The 1-based round (one stock round and its operating rounds)."""
    operating: int
    """The 1-based operating round within the round, or 0 for the stock round."""
    clock: float
    """Position on the clock described in the module docstring."""

    @property
    def is_stock(self) -> bool:
        return self.operating == 0


def round_point(label: str, operating_rounds_per_stock_round: int) -> RoundPoint:
    """The clock position of a session round label (``"SR3"``, ``"OR3.2"``). Labels for the
    setup and the end of the game have no position and raise ``ValueError``."""
    k = operating_rounds_per_stock_round
    stock = _STOCK_LABEL.match(label)
    if stock is not None:
        number = int(stock.group(1))
        return RoundPoint(number, 0, (number - 1) * k + 0.5)
    operating = _OPERATING_LABEL.match(label)
    if operating is not None:
        number, index = int(operating.group(1)), int(operating.group(2))
        return RoundPoint(number, index, float((number - 1) * k + index))
    raise ValueError(f"Round label {label!r} is not a stock or operating round")


def stock_round_before(clock: float, operating_rounds_per_stock_round: int) -> float:
    """Clock of the latest stock round at or before ``clock``."""
    k = operating_rounds_per_stock_round
    return math.floor((clock - 0.5) / k) * k + 0.5


@dataclass
class CorpDeathStarMetrics:
    fleets_bought: int = 0
    """Fleets bought; under the facility rules, facilities built (not the free home one)."""
    fleet_spend: int = 0
    """Total paid for fleets (or facilities)."""
    fleets_seized: int = 0
    final_fleets: int = 0
    contract_pairs: int = 0
    """Contract pairs scored over the game (one cube each)."""
    contract_revenue: int = 0
    """What those contract pairs earned, at the stage value when each was scored."""
    revenue_total: int = 0
    """All revenue over the game, paid or withheld."""
    closed: bool = False
    """The corporation went bankrupt."""
    closed_at: float = 0.0
    """Clock of the operating round in which it closed; 0 if it did not."""
    closed_round: int = 0
    """Round in which it closed; 0 if it did not."""
    closed_president: str = ""
    """Seat (player id) of its president when it closed; empty if it did not."""


@dataclass
class DeathStarMetrics:
    """What one game under the Death Star rules did with the track, fleets and contracts."""

    launched: bool
    """The station launched (the game ended by completion, not the backstop)."""
    stage_filled_at: tuple[float, ...]
    """Clock at which each stage filled, one entry per configured stage; 0 if it never did."""
    stage_resolved_at: tuple[float, ...]
    """Clock of the round at whose end each stage's result applied; 0 if it never did."""
    contract_cubes: int
    empire_cubes: int
    fleets_sold: int
    final_fleet_price: int
    final_fleet_tier: int
    """1-based tier the next fleet would come from at the end."""
    dividend_choices: int
    """Dividend decisions with positive revenue (zero revenue is a forced withhold)."""
    withholds: int
    dividend_choices_near_seizure: int
    """Dividend choices in the operating rounds near a seizure stage filling (see
    ``NEAR_SEIZURE_OPERATING_ROUNDS``)."""
    withholds_near_seizure: int
    sale_rounds: int
    """Stock rounds in which selling was allowed (every one but the first)."""
    shares_sold: int
    sale_rounds_before_stage: int
    """Of those, the stock rounds last before a seizure or site-move stage filled."""
    shares_sold_before_stage: int
    site_move_price_delta: int
    """Price change summed over corporations, from the last operating round ending at or before
    the site move to the first one ending after it."""
    site_move_price_corps: int
    """Corporations measured for ``site_move_price_delta`` (open at both ends)."""
    or_price_delta: int
    """Price change summed over corporations and every pair of consecutive operating-round
    ends: the baseline for ``site_move_price_delta``."""
    or_price_corps: int
    fleets_end_round: dict[int, int]
    """Fleets owned by open corporations at the end of each round played."""
    corps: dict[str, CorpDeathStarMetrics]
    """Every corporation, started or not."""

    @property
    def bankruptcies(self) -> int:
        return sum(1 for c in self.corps.values() if c.closed)

    @property
    def stages_filled(self) -> int:
        return sum(1 for t in self.stage_filled_at if t > 0)

    def to_row(self) -> dict[str, int | float | bool | str]:
        """Flat ``ds.*`` fields for a sweep row."""
        p = ROW_PREFIX
        row: dict[str, int | float | bool | str] = {
            f"{p}launched": self.launched,
            f"{p}stages_filled": self.stages_filled,
            f"{p}contract_cubes": self.contract_cubes,
            f"{p}empire_cubes": self.empire_cubes,
            f"{p}fleets_sold": self.fleets_sold,
            f"{p}final_fleet_price": self.final_fleet_price,
            f"{p}final_fleet_tier": self.final_fleet_tier,
            f"{p}bankruptcies": self.bankruptcies,
            f"{p}dividend_choices": self.dividend_choices,
            f"{p}withholds": self.withholds,
            f"{p}dividend_choices_near_seizure": self.dividend_choices_near_seizure,
            f"{p}withholds_near_seizure": self.withholds_near_seizure,
            f"{p}sale_rounds": self.sale_rounds,
            f"{p}shares_sold": self.shares_sold,
            f"{p}sale_rounds_before_stage": self.sale_rounds_before_stage,
            f"{p}shares_sold_before_stage": self.shares_sold_before_stage,
            f"{p}site_move_price_delta": self.site_move_price_delta,
            f"{p}site_move_price_corps": self.site_move_price_corps,
            f"{p}or_price_delta": self.or_price_delta,
            f"{p}or_price_corps": self.or_price_corps,
            f"{p}contract_revenue": sum(c.contract_revenue for c in self.corps.values()),
            f"{p}revenue_total": sum(c.revenue_total for c in self.corps.values()),
        }
        for index, (filled, resolved) in enumerate(
            zip(self.stage_filled_at, self.stage_resolved_at), start=1
        ):
            row[f"{p}stage{index}.filled_at"] = filled
            row[f"{p}stage{index}.resolved_at"] = resolved
        for number, fleets in sorted(self.fleets_end_round.items()):
            row[f"{p}fleets_end_round.{number}"] = fleets
        for corp_id, metrics in self.corps.items():
            for name, value in asdict(metrics).items():
                row[f"{p}corp.{corp_id}.{name}"] = value
        return row


@dataclass
class _Tally:
    choices: int = 0
    withholds: int = 0


class DeathStarRecorder:
    """A move observer (``MoveObserver``) for one game played under the Death Star rules.

    Pass it to ``GameSession.run_bots`` or ``apply``, then call ``metrics`` once the game is
    over. Every change to the track, fleets and prices happens inside some move, so comparing
    the state after each move with the state after the previous one attributes each change to
    the round it happened in. The cost per move is a few attribute reads; prices are read only
    when an operating round ends.
    """

    def __init__(self, game: Game) -> None:
        if not game.config.death_star_rules:
            raise ValueError("The Death Star recorder needs a game with death_star_rules on")
        self._config: GameConfig = game.config
        self._k = game.config.operating_rounds_per_stock_round
        track = game.death_star
        self._cubes = track.cubes
        self._filled = track.stages_filled(game.config)
        self._resolved = track.stages_resolved
        self._contract_value = game.contract_value()
        self._round_number = game.round_number
        self._fleets = {c.id: c.fleets for c in game.corporations.values()}
        self.corps = {corp_id: CorpDeathStarMetrics() for corp_id in game.corporations}
        self.stage_filled_at: list[float] = []
        self.stage_resolved_at: list[float] = []
        self.contract_cubes = 0
        self.empire_cubes = 0
        self._dividends: defaultdict[float, _Tally] = defaultdict(_Tally)
        self._sales: dict[float, int] = {}
        """Shares sold in each stock round where selling was allowed, by clock."""
        self._or_prices: list[tuple[float, dict[str, int]]] = []
        self.fleets_end_round: dict[int, int] = {}
        self.build_exits: Counter[str] = Counter()
        """Under the facility rules, each built facility by where its new exit went
        (``build_exit_kind``)."""

    def __call__(self, session: GameSession, move: PlayedMove) -> None:
        game = session.game
        point = round_point(move.round_label, self._k)
        if move.phase is Phase.STOCK:
            self._record_stock(point, move)
        elif move.phase is Phase.FLEET:
            self._record_fleet(game, move)
        elif move.phase is Phase.DIVIDEND:
            self._record_dividend(point, move)
        elif move.phase is Phase.NETWORK:
            if game.corp(move.corporation).status is CorpStatus.CLOSED:
                closed = self.corps[move.corporation]
                closed.closed = True
                closed.closed_at = point.clock
                closed.closed_round = point.round
                closed.closed_president = move.actor
        self._record_track(game, point, move)
        # Fleets rise in fleet moves and, under the facility rules, when a corporation floats
        # with its home facility; only a stage result lowers them, which _record_track counts.
        self._fleets = {c.id: c.fleets for c in game.corporations.values()}
        if point.operating and game.round_label != move.round_label:
            self._or_prices.append(
                (
                    point.clock,
                    {c.id: game.price(c) for c in game.corporations.values() if c.floated},
                )
            )
        while self._round_number < game.round_number:
            self._round_number += 1
            self.fleets_end_round[self._round_number] = sum(
                c.fleets for c in game.corporations.values() if c.floated
            )

    def _record_stock(self, point: RoundPoint, move: PlayedMove) -> None:
        if point.round < 2:
            return  # no sales in the first stock round
        sold = move.action.count if isinstance(move.action, SellShares) else 0
        self._sales[point.clock] = self._sales.get(point.clock, 0) + sold

    def _record_fleet(self, game: Game, move: PlayedMove) -> None:
        if isinstance(move.action, (BuyFleet, BuildFacility)):
            corp = self.corps[move.corporation]
            corp.fleets_bought += 1
            corp.fleet_spend += move.action.cost
        if isinstance(move.action, BuildFacility):
            self.build_exits[build_exit_kind(game, move.corporation, move.action)] += 1

    def _record_dividend(self, point: RoundPoint, move: PlayedMove) -> None:
        self.corps[move.corporation].revenue_total += move.revenue
        if move.revenue > 0:
            tally = self._dividends[point.clock]
            tally.choices += 1
            tally.withholds += int(move.action is Dividend.WITHHOLD)

    def _record_track(self, game: Game, point: RoundPoint, move: PlayedMove) -> None:
        track = game.death_star
        added = track.cubes - self._cubes
        if added:
            if move.phase is Phase.DIVIDEND:
                # Only a corporation's settlement adds cubes in an operating round, and it scores
                # its contracts at the value of the stage being built before the move.
                corp = self.corps[move.corporation]
                corp.contract_pairs += added
                corp.contract_revenue += added * self._contract_value
                self.contract_cubes += added
            else:
                self.empire_cubes += added
            self._cubes = track.cubes
        filled = track.stages_filled(self._config)
        self.stage_filled_at.extend([point.clock] * (filled - self._filled))
        self._filled = filled
        if track.stages_resolved != self._resolved:
            self.stage_resolved_at.extend([point.clock] * (track.stages_resolved - self._resolved))
            self._resolved = track.stages_resolved
            for state in game.corporations.values():
                lost = self._fleets[state.id] - state.fleets
                if lost > 0:
                    self.corps[state.id].fleets_seized += lost
        self._contract_value = game.contract_value()

    def metrics(self, game: Game) -> DeathStarMetrics:
        """Summarize the finished game."""
        results = self._config.death_star_stage_results
        stage_count = len(results)
        near_rounds = {
            clock
            for index, filled in enumerate(self.stage_filled_at)
            if results[index] == SEIZURE
            for clock in self._dividends
            if filled - NEAR_SEIZURE_OPERATING_ROUNDS < clock <= filled
        }
        before_stage = {
            stock_round_before(filled, self._k)
            for index, filled in enumerate(self.stage_filled_at)
            if results[index] in SALE_BEFORE_STAGE_RESULTS
        } & set(self._sales)
        site_delta, site_corps = self._site_move_prices(results)
        or_delta, or_corps = 0, 0
        for (_, before), (_, after) in zip(self._or_prices, self._or_prices[1:]):
            delta, count = _price_change(before, after)
            or_delta += delta
            or_corps += count
        for corp in game.corporations.values():
            self.corps[corp.id].final_fleets = corp.fleets
        return DeathStarMetrics(
            launched=game.death_star.launched,
            stage_filled_at=_pad(self.stage_filled_at, stage_count),
            stage_resolved_at=_pad(self.stage_resolved_at, stage_count),
            contract_cubes=self.contract_cubes,
            empire_cubes=self.empire_cubes,
            fleets_sold=game.fleets_sold,
            final_fleet_price=game.fleet_price(),
            final_fleet_tier=game.fleet_tier() + 1,
            dividend_choices=sum(t.choices for t in self._dividends.values()),
            withholds=sum(t.withholds for t in self._dividends.values()),
            dividend_choices_near_seizure=sum(self._dividends[c].choices for c in near_rounds),
            withholds_near_seizure=sum(self._dividends[c].withholds for c in near_rounds),
            sale_rounds=len(self._sales),
            shares_sold=sum(self._sales.values()),
            sale_rounds_before_stage=len(before_stage),
            shares_sold_before_stage=sum(self._sales[c] for c in before_stage),
            site_move_price_delta=site_delta,
            site_move_price_corps=site_corps,
            or_price_delta=or_delta,
            or_price_corps=or_corps,
            fleets_end_round=dict(self.fleets_end_round),
            corps=self.corps,
        )

    def facility_metrics(self, game: Game) -> FacilityMetrics:
        """Summarize the finished game's facilities and planet exits; the game must be under
        the facility rules."""
        return facility_metrics(game, self.build_exits)

    def _site_move_prices(self, results: tuple[str, ...]) -> tuple[int, int]:
        moves = [
            resolved
            for index, resolved in enumerate(self.stage_resolved_at)
            if results[index] == SITE_MOVE
        ]
        delta, count = 0, 0
        for moved in moves:
            before = [prices for clock, prices in self._or_prices if clock <= moved]
            after = [prices for clock, prices in self._or_prices if clock > moved]
            if before and after:
                d, n = _price_change(before[-1], after[0])
                delta += d
                count += n
        return delta, count


def _price_change(before: dict[str, int], after: dict[str, int]) -> tuple[int, int]:
    """Summed price change and count over corporations priced at both moments."""
    common = before.keys() & after.keys()
    return sum(after[c] - before[c] for c in common), len(common)


def _pad(values: list[float], length: int) -> tuple[float, ...]:
    return tuple(values) + (0.0,) * (length - len(values))
