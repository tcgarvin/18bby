"""Experimental Death Star rules: construction-site placement, the construction track and the
shared fleet supply (see "Death Star and fleets" in docs/DECISIONS.md).

Only state and pure helpers live here. ``Game`` enforces the rules and applies their
consequences; ``GameSession`` decides when each step happens.
"""

from __future__ import annotations

import random
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


def describe_result(result: str) -> str:
    """What a stage result does, in a few words for logs."""
    descriptions = {
        SEIZURE: "the Empire seizes a fleet from every corporation that has one",
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
    empty space hex at least ``death_star_min_homeworld_distance`` from every homeworld and
    ``death_star_min_planet_distance`` from every planet, with at least
    ``death_star_min_chartable_neighbors`` neighbours that could be charted (not planets,
    asteroid fields or the other site). Raises ``SitePlacementError`` if no hex qualifies.
    """
    rng = random.Random(f"death-star:{seed}")
    first_region, second_region = config.death_star_site_regions
    firsts = [h for h in board.space_hexes() if _qualifies(board, config, h, first_region)]
    if not firsts:
        raise SitePlacementError(f"No hex qualifies for the first site in {first_region}")
    first = rng.choice(firsts)
    seconds = [
        h
        for h in board.space_hexes()
        if h != first
        and _qualifies(board, config, h, second_region, other_sites=frozenset({first}))
        and _qualifies(board, config, first, first_region, other_sites=frozenset({h}))
    ]
    if not seconds:
        raise SitePlacementError(
            f"No hex qualifies for the second site in {second_region} (first site {first})"
        )
    return first, rng.choice(seconds)


def _qualifies(
    board: Board,
    config: GameConfig,
    hex: Hex,
    region: str,
    other_sites: frozenset[Hex] = frozenset(),
) -> bool:
    """Whether ``hex`` can hold a site in ``region``, given the other sites placed so far."""
    if board.is_planet(hex) or board.terrain_at(hex) is not Terrain.SPACE:
        return False
    if board.region_of(hex) != region:
        return False
    homeworlds = [board.planet_named(c.homeworld).hex for c in config.corporations]
    if any(hex.distance(h) < config.death_star_min_homeworld_distance for h in homeworlds):
        return False
    if any(hex.distance(p.hex) < config.death_star_min_planet_distance for p in board.planets):
        return False
    chartable = [
        n for _, n in board.neighbors(hex) if not board.is_planet(n) and n not in other_sites
    ]
    return len(chartable) >= config.death_star_min_chartable_neighbors
