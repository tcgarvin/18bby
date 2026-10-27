"""Per-game measurements of the facility rules, for balance sweeps.

``FacilityMetrics.to_row`` gives the flat ``fac.*`` fields of a sweep row; games without the
facility rules have none. Most fields read the finished game: its facilities, planet exits and
dangling lanes. Where each built facility's new exit went is tallied while the game is played,
by ``DeathStarRecorder`` with ``build_exit_kind``, since a later chart can claim an exit left
unclaimed. The per-corporation facility counts are the ``ds.corp.*`` fleet fields, which count
facilities under these rules (``fleets_bought`` excludes the free home facility).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

from bby18.actions import BuildFacility
from bby18.game import EMPIRE, Game

ROW_PREFIX = "fac."
"""Every facility row field starts with this; rows of games without the facility rules have
none."""

OWN_LANE = "own_lane"
"""A build gave its new exit to a dangling lane on a tile the builder serves."""
RIVAL_LANE = "rival_lane"
"""A build gave its new exit to a dangling lane on a tile only other corporations serve."""
UNCLAIMED = "unclaimed"
"""A build left its new exit unclaimed, for the next tile charted toward the planet."""
BUILD_EXIT_KINDS = (OWN_LANE, RIVAL_LANE, UNCLAIMED)


def build_exit_kind(game: Game, corp_id: str, action: BuildFacility) -> str:
    """Where ``action``'s new exit went, one of ``BUILD_EXIT_KINDS``. Service does not change in
    the facility step, so this reads the same before and after the build."""
    if action.exit_side is None:
        return UNCLAIMED
    lane = action.planet.neighbor(action.exit_side)
    return OWN_LANE if corp_id in game.network.corporations_serving(lane) else RIVAL_LANE


@dataclass(frozen=True)
class FacilityMetrics:
    """What one game under the facility rules did with facilities and planet exits."""

    home_facilities: int
    """Free facilities placed on homeworlds as corporations floated."""
    facilities_built: int
    """Facilities bought from the supply (the home ones are not)."""
    exits_to_own_lanes: int
    """Built facilities whose new exit went to a lane the builder serves."""
    exits_to_rival_lanes: int
    """Built facilities whose new exit went to a lane only rivals serve."""
    exits_left_unclaimed: int
    """Built facilities whose new exit was left for the next tile charted toward the planet."""
    corporate_facilities: int
    """Facilities corporations own at the end: slots they fill."""
    imperial_facilities: int
    """Facilities the Empire has taken over by the end: slots it fills for good."""
    seizure_ties: int
    """Seizures decided by the most-recently-built tie-break between planets
    (``Game.facility_seizure_ties``)."""
    limited_planets: int
    """Planets with limited exits: every planet but the construction site."""
    planet_exits: int
    """Exits of those planets at the end, claimed or not."""
    planets_at_base_exits: int
    """Planets that never got a facility, so still have only their base exits (1 by default)."""
    claimed_exits: int
    unclaimed_exits: int
    """Exits no lane had claimed by the end."""
    dangling_lanes: int
    """Lanes facing a planet that has not claimed them at the end."""
    connected_planets: int
    """Planets with at least one claimed exit at the end: some lane connects there."""

    def to_row(self) -> dict[str, int]:
        """Flat ``fac.*`` fields for a sweep row."""
        return {f"{ROW_PREFIX}{name}": value for name, value in asdict(self).items()}


def facility_metrics(game: Game, build_exits: Counter[str]) -> FacilityMetrics:
    """Summarize a finished game under the facility rules. ``build_exits`` counts each built
    facility by ``build_exit_kind``."""
    if not game.config.facility_rules:
        raise ValueError("Facility metrics need a game with facility_rules on")
    unknown = sorted(set(build_exits) - set(BUILD_EXIT_KINDS))
    if unknown:
        raise ValueError(f"Unknown build exit kinds {unknown}")
    net = game.network
    limited = [p.hex for p in game.board.planets if net.has_exit_limit(p.hex)]
    base = game.config.planet_base_exits
    imperial = sum(1 for f in game.facilities if f.owner == EMPIRE)
    return FacilityMetrics(
        home_facilities=sum(1 for c in game.corporations.values() if c.float_order >= 0),
        facilities_built=game.fleets_sold,
        exits_to_own_lanes=build_exits[OWN_LANE],
        exits_to_rival_lanes=build_exits[RIVAL_LANE],
        exits_left_unclaimed=build_exits[UNCLAIMED],
        corporate_facilities=len(game.facilities) - imperial,
        imperial_facilities=imperial,
        seizure_ties=game.facility_seizure_ties,
        limited_planets=len(limited),
        planet_exits=sum(net.planet_exits(h) for h in limited),
        planets_at_base_exits=sum(1 for h in limited if net.planet_exits(h) == base),
        claimed_exits=sum(len(net.claimed_exits(h)) for h in limited),
        unclaimed_exits=sum(net.unclaimed_exits(h) for h in limited),
        dangling_lanes=sum(len(net.dangling_sides(h)) for h in limited),
        connected_planets=sum(1 for h in limited if net.claimed_exits(h)),
    )
