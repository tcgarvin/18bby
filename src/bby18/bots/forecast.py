"""What a bot expects of the Death Star track: how long the game will last, when the next
seizure comes and what a fleet will cost. Only meaningful under the experimental Death Star
rules (``GameConfig.death_star_rules``); bots consult it only then.

Every forecast reads the current state only. The cube rate is the rate of the track right now:
the contract pairs every floated corporation's current revenue would score in one operating
round, plus the Empire's cubes at the end of each round.
"""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass

from bby18.config import COMPLETION, SEIZURE, SITE_MOVE, Unlimited
from bby18.death_star import fleet_price, fleet_tier_index
from bby18.game import Game
from bby18.state import CorpStatus

NOTHING_AHEAD = sys.maxsize
"""Operating rounds or cubes until a stage result that will not come."""
SEIZURE_MARGIN_CUBES = 2
"""Extra cubes allowed for when judging how soon a seizure could come: a bot would rather keep
a reserve one cube early than lose its corporation one cube late."""
MIN_EXPECTED_TURNS = 2
"""Floor on the estimate of operating turns left from the cube rate (the backstop still caps
it): the rate is noisy, and a station is rarely finished in one round."""
RESERVE_HORIZON_TURNS = 6
"""A seizure further off than this many operating rounds needs no reserve yet: revenue will
change before then, and a corporation earning little now would otherwise hoard for it."""
TIER_NEARLY_SOLD = 2
"""A fleet tier with this many fleets or fewer left is treated as sold out when a bot prices
the fleet it may need later: rivals may buy them first."""

_OPERATING_LABEL = re.compile(r"^OR\d+\.(\d+)$")


def operating_round_index(game: Game) -> int:
    """0-based index of the operating round being played within its round; 0 outside
    operating rounds (the next one is then the round's first)."""
    match = _OPERATING_LABEL.match(game.round_label)
    return int(match.group(1)) - 1 if match else 0


def turns_to_round_limit(game: Game) -> int:
    """Operating turns each corporation has left, the current one included, if the game runs to
    ``round_limit``."""
    per_round = game.config.operating_rounds_per_stock_round
    rounds_left = game.round_limit() - game.round_number
    return max(0, rounds_left * per_round - operating_round_index(game))


def contract_cubes_per_operating_round(game: Game) -> int:
    """Cubes the floated corporations' current revenue would add in one operating round."""
    return sum(
        game.revenue(corp).contract_pairs
        for corp in game.corporations.values()
        if corp.status is CorpStatus.FLOATED
    )


def cubes_until(game: Game, result: str) -> int:
    """Cubes still needed to fill the next unresolved stage with ``result``; 0 or less when it
    has filled and waits for the end of the round; ``NOTHING_AHEAD`` when no such stage
    remains."""
    config = game.config
    track = game.death_star
    for index in range(track.stages_resolved, len(config.death_star_stage_results)):
        if config.death_star_stage_results[index] == result:
            return (index + 1) * config.death_star_cubes_per_stage - track.cubes
    return NOTHING_AHEAD


def operating_rounds_until(game: Game, needed: int, contract_rate: float, margin: int) -> int:
    """Operating rounds, the current one included, by the end of which ``needed`` more cubes
    are on the track at ``contract_rate`` cubes per operating round plus the Empire's cubes
    (``margin`` cubes are counted as already there). A stage filled by the Empire after the
    last of them applies at the end of that stock round, before the next operating round, so it
    counts as that round's. ``NOTHING_AHEAD`` if not before the round limit."""
    if needed == NOTHING_AHEAD:
        return NOTHING_AHEAD
    if needed <= 0:
        return 1
    config = game.config
    per_round = config.operating_rounds_per_stock_round
    index = operating_round_index(game)
    cubes: float = margin
    for k in range(1, turns_to_round_limit(game) + 1):
        cubes += contract_rate
        if (index + k) % per_round == 0:
            cubes += config.empire_cubes_per_stock_round
        if cubes >= needed:
            return k
    return NOTHING_AHEAD


def next_fleet_prices(game: Game, count: int) -> list[int]:
    """What the next ``count`` fleets from the supply would cost, bought in a row."""
    tiers = game.config.fleet_tiers
    return [fleet_price(tiers, game.fleets_sold + n) for n in range(count)]


def cautious_fleet_price(game: Game) -> int:
    """The price to set aside for a fleet needed at a later fleet step: the current price, or
    the next tier's if the current tier is nearly sold out."""
    tiers = game.config.fleet_tiers
    index = fleet_tier_index(tiers, game.fleets_sold)
    tier = tiers[index]
    if isinstance(tier.count, Unlimited):
        return tier.price
    sold_before = 0
    for earlier in tiers[:index]:
        assert not isinstance(earlier.count, Unlimited)
        sold_before += earlier.count
    left = sold_before + tier.count - game.fleets_sold
    if left <= TIER_NEARLY_SOLD:
        return tiers[index + 1].price
    return tier.price


@dataclass(frozen=True)
class TrackForecast:
    """One reading of the track for one decision; build it with ``TrackForecast.of``."""

    turns_left: int
    """Operating turns each corporation can expect, the current one included: the turns to the
    backstop, or fewer if the cube rate says the station will launch sooner (the game then
    ends with the round it launches in)."""
    site_turns_left: int
    """Expected operating turns, the current one included, that the active site stays put."""
    rounds_to_site_move: int
    """Expected operating rounds, the current one included, until the site moves."""
    seizure_deadline: int
    """Operating rounds, the current one included, by the end of which a seizure could have
    applied, judged pessimistically (``SEIZURE_MARGIN_CUBES``); ``NOTHING_AHEAD`` if none
    can before the game ends."""
    seizure_within_round: bool
    """Whether a seizure could apply before the end of the next round's operating rounds; for
    decisions in a stock round."""
    cautious_price: int
    """See ``cautious_fleet_price``."""

    @classmethod
    def of(cls, game: Game) -> TrackForecast:
        rate = contract_cubes_per_operating_round(game)
        per_round = game.config.operating_rounds_per_stock_round
        backstop = turns_to_round_limit(game)
        turns_left = backstop
        if not game.death_star.launched:
            to_launch = operating_rounds_until(game, cubes_until(game, COMPLETION), rate, 0)
            if to_launch != NOTHING_AHEAD:
                index = operating_round_index(game)
                through_round_end = math.ceil((index + to_launch) / per_round) * per_round - index
                turns_left = min(backstop, max(MIN_EXPECTED_TURNS, through_round_end))
        to_move = operating_rounds_until(game, cubes_until(game, SITE_MOVE), rate, 0)
        site_turns = min(turns_left, to_move) if game.death_star.reserved_sites else turns_left
        seizure_needed = cubes_until(game, SEIZURE)
        deadline = operating_rounds_until(game, seizure_needed, rate, SEIZURE_MARGIN_CUBES)
        within_round = seizure_needed <= (
            game.config.empire_cubes_per_stock_round + per_round * rate + SEIZURE_MARGIN_CUBES
        )
        return cls(
            turns_left=turns_left,
            site_turns_left=site_turns,
            rounds_to_site_move=to_move,
            seizure_deadline=deadline,
            seizure_within_round=within_round,
            cautious_price=cautious_fleet_price(game),
        )

    @property
    def seizure_before_next_fleet_step(self) -> bool:
        """Whether a seizure could apply before a corporation operating now reaches its next
        fleet step."""
        return self.seizure_deadline == 1

    def fleet_reserve(self, fleets: int, revenue: int) -> int:
        """What a corporation that will own ``fleets`` after this turn, earning ``revenue`` a
        turn, must keep in its treasury now so that a seizure cannot leave it unable to replace
        its last fleet: a replacement's price, less what it can still withhold before the
        seizure applies. 0 when a seizure cannot leave it fleetless, or is more than
        ``RESERVE_HORIZON_TURNS`` away."""
        if fleets > 1 or self.seizure_deadline > RESERVE_HORIZON_TURNS:
            return 0
        later_turns = self.seizure_deadline - 1
        return max(0, self.cautious_price - later_turns * revenue)


def is_fragile(game: Game, corp_id: str, forecast: TrackForecast) -> bool:
    """Whether a floated corporation may close in the coming round: it owns no fleet and cannot
    buy one, or owns one and cannot replace it when a seizure looks likely."""
    corp = game.corp(corp_id)
    if corp.status is not CorpStatus.FLOATED:
        return False
    if corp.fleets == 0:
        return corp.treasury < game.fleet_price()
    return (
        corp.fleets == 1
        and corp.treasury < forecast.cautious_price
        and forecast.seizure_within_round
    )
