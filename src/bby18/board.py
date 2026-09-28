"""The fixed board: hexes, planets, regions and economic tags, loaded from the map JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources

from bby18.hexgrid import Hex, hexes_within_radius


@dataclass(frozen=True)
class Planet:
    name: str
    hex: Hex
    region: str
    tags: frozenset[str]


class Board:
    """Immutable board geometry with planet lookups by hex and by name."""

    def __init__(self, radius: int, hexes: frozenset[Hex], planets: tuple[Planet, ...]) -> None:
        self.radius = radius
        self.hexes = hexes
        self.planets = planets
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

    def contains(self, hex: Hex) -> bool:
        return hex in self.hexes

    def is_planet(self, hex: Hex) -> bool:
        return hex in self._by_hex

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
