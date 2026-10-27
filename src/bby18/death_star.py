"""The Death Star rules: construction-site placement, the construction track and the
shared fleet supply (see "Death Star and fleets" in docs/DECISIONS.md). Under the facility rules
the same supply prices facilities.

Only state and pure helpers live here. ``Game`` enforces the rules and applies their
consequences; ``GameSession`` decides when each step happens.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from bby18.board import Board, Planet, Terrain
from bby18.config import COMPLETION, SEIZURE, SITE_MOVE, FleetTier, GameConfig, Unlimited
from bby18.hexgrid import Hex

SITE_NAME = "Death Star"
"""Planet name of the active construction site."""
STAGE_NAMES = ("Frame", "Superstructure", "Superlaser", "Completion")
"""Names of the stages in the designed four-stage track, for logs."""


class SitePlacementError(ValueError):
    """No hex on the board satisfies the construction-site constraints."""


@dataclass
class DeathStarTrack:
    """The construction sites and the cubes on the Death Star track.

    With the Death Star rules off a game holds the default, inactive track: no sites, no cubes.
    """

    sites: tuple[Hex, ...] = ()
    """Every construction site in the order the station uses them; all are shown from the
    start."""
    site_index: int = 0
    """Index in ``sites`` of the site under construction."""
    launched: bool = False
    """The station has launched and left the board."""
    cubes: int = 0
    """Cubes on the track, carried over across stages."""
    stages_resolved: int = 0
    """Stages whose result has applied. The stage after them is the one being built."""
    final_round: int = 0
    """The game ends once ``Game.round_number`` reaches this: the backstop, or the round after
    the one in which the station launched. Only meaningful with the Death Star rules on."""

    @property
    def active_site(self) -> Hex | None:
        """The hex of the site under construction, or ``None`` if there is none (rules off, or
        the station has launched)."""
        if self.launched or not self.sites:
            return None
        return self.sites[self.site_index]

    @property
    def reserved_sites(self) -> tuple[Hex, ...]:
        """Future sites: shown, unchartable, not yet planets."""
        if self.launched:
            return ()
        return self.sites[self.site_index + 1 :]

    def stages_filled(self, config: GameConfig) -> int:
        """Stages whose cubes are all on the track, resolved or not."""
        return min(
            self.cubes // config.death_star_cubes_per_stage, len(config.death_star_stage_results)
        )


def stage_name(index: int) -> str:
    """A stage's name for logs; ``index`` is 0-based."""
    if 0 <= index < len(STAGE_NAMES):
        return f"stage {index + 1} ({STAGE_NAMES[index]})"
    return f"stage {index + 1}"


def describe_result(result: str, config: GameConfig) -> str:
    """What a stage result does, in a few words for logs."""
    seized = "takes over a facility" if config.facility_rules else "seizes a fleet"
    descriptions = {
        SEIZURE: f"the Empire {seized} from every corporation that has one",
        SITE_MOVE: "the construction site moves",
        COMPLETION: "the station launches",
    }
    return descriptions[result]


def fleet_tier_index(tiers: tuple[FleetTier, ...], sold: int) -> int:
    """Index of the tier the next fleet comes from after ``sold`` fleets have been sold."""
    remaining = sold
    for index, tier in enumerate(tiers):
        if isinstance(tier.count, Unlimited) or remaining < tier.count:
            return index
        remaining -= tier.count
    raise ValueError("fleet_tiers must end with an UNLIMITED tier")


def fleet_price(tiers: tuple[FleetTier, ...], sold: int) -> int:
    """Price of the next fleet after ``sold`` fleets have been sold."""
    return tiers[fleet_tier_index(tiers, sold)].price


def site_planet(board: Board, hex: Hex, config: GameConfig) -> Planet:
    """The construction site at ``hex`` as a planet of ``board`` (a board without it)."""
    return Planet(SITE_NAME, hex, board.region_of(hex), frozenset({config.death_star_tag}))


def place_sites(board: Board, seed: int, config: GameConfig) -> tuple[Hex, Hex]:
    """The two construction sites for ``seed``, drawn from their own random stream so terrain
    placement is unaffected.

    The first site is in ``death_star_site_regions[0]``, the second in ``[1]``. Each is an
    empty space hex at least ``death_star_min_homeworld_distance`` from every homeworld, within
    ``death_star_max_homeworld_distance`` of at least ``death_star_near_homeworlds`` of them, and
    ``death_star_min_planet_distance`` from every planet, with at least
    ``death_star_min_chartable_neighbors`` neighbours that could be charted (not planets,
    asteroid fields or the other site). If no hex is near enough to the homeworlds, the
    distance limit is relaxed one hex at a time. Raises ``SitePlacementError`` if no hex
    qualifies at any distance.
    """
    rng = random.Random(f"death-star:{seed}")
    first_region, second_region = config.death_star_site_regions
    first = rng.choice(
        _candidates(
            board,
            config,
            lambda h, reach: _qualifies(board, config, h, first_region, reach),
            f"the first site in {first_region}",
        )
    )

    def second_qualifies(h: Hex, reach: int) -> bool:
        return (
            h != first
            and _qualifies(board, config, h, second_region, reach, frozenset({first}))
            and _qualifies(board, config, first, first_region, _NO_REACH, frozenset({h}))
        )

    seconds = _candidates(
        board, config, second_qualifies, f"the second site in {second_region} (first {first})"
    )
    return first, rng.choice(seconds)


_NO_REACH = 1_000
"""A reach larger than any board: no limit on distance to homeworlds."""


def _candidates(
    board: Board, config: GameConfig, qualifies: Callable[[Hex, int], bool], what: str
) -> list[Hex]:
    """Space hexes that qualify, relaxing ``death_star_max_homeworld_distance`` one hex at a
    time when none do, so that a tight limit never leaves a seed without a site."""
    reach = config.death_star_max_homeworld_distance
    while True:
        found = [h for h in board.space_hexes() if qualifies(h, reach)]
        if found:
            return found
        if reach >= 4 * board.radius:
            raise SitePlacementError(f"No hex qualifies for {what}")
        reach += 1


def _qualifies(
    board: Board,
    config: GameConfig,
    hex: Hex,
    region: str,
    reach: int,
    other_sites: frozenset[Hex] = frozenset(),
) -> bool:
    """Whether ``hex`` can hold a site in ``region``, given the other sites placed so far and
    ``reach``, the distance within which enough homeworlds must lie."""
    if board.is_planet(hex) or board.terrain_at(hex) is not Terrain.SPACE:
        return False
    if board.region_of(hex) != region:
        return False
    homeworlds = [board.planet_named(c.homeworld).hex for c in config.corporations]
    distances = [hex.distance(h) for h in homeworlds]
    if min(distances) < config.death_star_min_homeworld_distance:
        return False
    near = sum(1 for d in distances if d <= reach)
    if near < config.death_star_near_homeworlds:
        return False
    if any(hex.distance(p.hex) < config.death_star_min_planet_distance for p in board.planets):
        return False
    chartable = [
        n for _, n in board.neighbors(hex) if not board.is_planet(n) and n not in other_sites
    ]
    return len(chartable) >= config.death_star_min_chartable_neighbors
