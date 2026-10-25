"""The fixed board: hexes, planets, regions and economic tags, loaded from the map JSON."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from importlib import resources

from bby18.hexgrid import Direction, Hex, hexes_within_radius


class Terrain(Enum):
    """What fills a non-planet hex. Planets have no terrain."""

    SPACE = "space"
    ASTEROID = "asteroid"
    """Impassable: never charted, and no tile may have an exit facing it."""
    NEBULA = "nebula"
    """Costs extra to chart and can never be upgraded to three exits."""


@dataclass(frozen=True)
class Planet:
    name: str
    hex: Hex
    region: str
    tags: frozenset[str]


class Board:
    """Immutable board geometry with planet lookups by hex and by name."""

    def __init__(
        self,
        radius: int,
        hexes: frozenset[Hex],
        planets: tuple[Planet, ...],
        terrain: Mapping[Hex, Terrain] | None = None,
    ) -> None:
        self.radius = radius
        self.hexes = hexes
        self.planets = planets
        self.terrain: dict[Hex, Terrain] = {
            h: t for h, t in (terrain or {}).items() if t is not Terrain.SPACE
        }
        self._by_hex: dict[Hex, Planet] = {}
        self._by_name: dict[str, Planet] = {}
        for planet in planets:
            if planet.hex not in hexes:
                raise ValueError(f"Planet {planet.name} at {planet.hex} is off the board")
            if planet.hex in self._by_hex:
                raise ValueError(f"Two planets share hex {planet.hex}")
            if planet.name in self._by_name:
                raise ValueError(f"Duplicate planet name {planet.name}")
            self._by_hex[planet.hex] = planet
            self._by_name[planet.name] = planet
        for hex, kind in self.terrain.items():
            if hex not in hexes:
                raise ValueError(f"{kind.value} at {hex} is off the board")
            if hex in self._by_hex:
                raise ValueError(f"{kind.value} at {hex} shares a hex with a planet")
        self._asteroids = frozenset(h for h, t in self.terrain.items() if t is Terrain.ASTEROID)
        # Geometry never changes, so adjacency is computed once for fast searches. Asteroid
        # fields are not neighbors of anything: nothing can be charted there or routed through.
        self._neighbors: dict[Hex, tuple[tuple[Direction, Hex], ...]] = {
            h: tuple((d, n) for d, n in h.neighbors() if n in hexes and n not in self._asteroids)
            for h in hexes
        }
        self._exits: dict[Hex, frozenset[Direction]] = {
            h: frozenset(d for d, _ in pairs) for h, pairs in self._neighbors.items()
        }

    def contains(self, hex: Hex) -> bool:
        return hex in self.hexes

    def neighbors(self, hex: Hex) -> tuple[tuple[Direction, Hex], ...]:
        """Adjacent hexes that are on the board, with the direction to each."""
        pairs = self._neighbors.get(hex)
        if pairs is None:
            return tuple(
                (d, n) for d, n in hex.neighbors() if n in self.hexes and n not in self._asteroids
            )
        return pairs

    def on_board_directions(self, hex: Hex) -> frozenset[Direction]:
        """Directions from ``hex`` that face a hex a tile could connect to: on the board and not
        an asteroid field."""
        exits = self._exits.get(hex)
        if exits is None:
            return frozenset(d for d, _ in self.neighbors(hex))
        return exits

    def is_planet(self, hex: Hex) -> bool:
        return hex in self._by_hex

    def terrain_at(self, hex: Hex) -> Terrain:
        return self.terrain.get(hex, Terrain.SPACE)

    def with_terrain(self, terrain: Mapping[Hex, Terrain]) -> Board:
        """The same board with ``terrain`` laid over its space hexes."""
        return Board(self.radius, self.hexes, self.planets, terrain)

    def planet_at(self, hex: Hex) -> Planet:
        try:
            return self._by_hex[hex]
        except KeyError:
            raise KeyError(f"No planet at {hex}") from None

    def planet_named(self, name: str) -> Planet:
        try:
            return self._by_name[name]
        except KeyError:
            raise KeyError(f"No planet named {name!r}") from None

    def space_hexes(self) -> list[Hex]:
        return sorted(h for h in self.hexes if h not in self._by_hex)


def load_board(map_file: str = "map-127.json") -> Board:
    """Load a board from a bundled map JSON file."""
    text = resources.files("bby18.data").joinpath(map_file).read_text(encoding="utf-8")
    return board_from_json(json.loads(text))


def board_from_json(data: dict[str, object]) -> Board:
    map_data = data["map"]
    if not isinstance(map_data, dict):
        raise ValueError("Map JSON is missing the 'map' object")
    radius = int(map_data["radius"])
    hexes = frozenset(hexes_within_radius(radius))
    raw_cells = map_data["cells"]
    if not isinstance(raw_cells, list):
        raise ValueError("Map JSON 'cells' must be a list")
    cells = frozenset(Hex(int(c[0]), int(c[1])) for c in raw_cells)
    if cells != hexes:
        raise ValueError("Map cells do not match a hexagonal board of the stated radius")
    raw_planets = map_data["planets"]
    if not isinstance(raw_planets, list):
        raise ValueError("Map JSON 'planets' must be a list")
    planets = tuple(
        Planet(
            name=str(p["name"]),
            hex=Hex(int(p["position"][0]), int(p["position"][1])),
            region=str(p["region"]),
            tags=frozenset(str(p["tag"]).split("/")),
        )
        for p in raw_planets
    )
    return Board(radius=radius, hexes=hexes, planets=planets)
