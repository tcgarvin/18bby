"""The shared hyperspace network and each corporation's service layer.

Charted tiles are shared geometry. Service is per corporation. Planets are open hubs:
they have every exit and never need charting or service.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from bby18.board import Board
from bby18.hexgrid import Direction, Hex

_OPPOSITE: dict[Direction, Direction] = {d: d.opposite for d in Direction}


class IllegalAction(Exception):
    """Raised when a requested network change is not legal."""


@dataclass(frozen=True)
class Tile:
    exits: frozenset[Direction]

    @property
    def level(self) -> int:
        return len(self.exits) - 1


class HyperspaceNetwork:
    """Charted tiles plus, for each corporation id, the set of tiles it has service on."""

    MAX_EXITS = 3

    def __init__(self, board: Board) -> None:
        self.board = board
        self._tiles: dict[Hex, Tile] = {}
        self._service: dict[str, set[Hex]] = {}

    def copy(self) -> HyperspaceNetwork:
        """A cheap copy sharing the immutable board, for what-if evaluation."""
        clone = HyperspaceNetwork(self.board)
        clone._tiles = dict(self._tiles)
        clone._service = {c: set(h) for c, h in self._service.items()}
        return clone

    # --- queries -------------------------------------------------------------

    def tile_at(self, hex: Hex) -> Tile | None:
        return self._tiles.get(hex)

    def is_charted(self, hex: Hex) -> bool:
        return hex in self._tiles

    def tiles(self) -> dict[Hex, Tile]:
        return dict(self._tiles)

    def service_of(self, corp: str) -> frozenset[Hex]:
        return frozenset(self._service.get(corp, ()))

    def corporations_serving(self, hex: Hex) -> frozenset[str]:
        return frozenset(c for c, hexes in self._service.items() if hex in hexes)

    def has_exit(self, hex: Hex, direction: Direction) -> bool:
        """Whether ``hex`` can carry traffic out of ``direction``. Planets always can."""
        if self.board.is_planet(hex):
            return True
        tile = self._tiles.get(hex)
        return tile is not None and direction in tile.exits

    def connected(self, a: Hex, b: Hex) -> bool:
        """Adjacent hexes are connected when each has an exit facing the other."""
        direction = a.direction_to(b)
        return self.has_exit(a, direction) and self.has_exit(b, direction.opposite)

    def reachable(self, corp: str, origin: Hex) -> frozenset[Hex]:
        """All hexes ``corp`` can reach from ``origin`` through its own service."""
        service = self._service.get(corp, set())
        board = self.board
        seen = {origin}
        queue = deque([origin])
        while queue:
            current = queue.popleft()
            for direction, nxt in board.neighbors(current):
                if nxt in seen:
                    continue
                if not board.is_planet(nxt) and nxt not in service:
                    continue
                if self.has_exit(current, direction) and self.has_exit(nxt, _OPPOSITE[direction]):
                    seen.add(nxt)
                    queue.append(nxt)
        return frozenset(seen)

    def legal_exits(self, hex: Hex) -> frozenset[Direction]:
        """Exits that face an on-board hex."""
        return self.board.on_board_directions(hex)

    # --- legality ------------------------------------------------------------

    def check_chart(
        self, corp: str, hex: Hex, exits: frozenset[Direction], reachable: frozenset[Hex]
    ) -> None:
        if not self.board.contains(hex):
            raise IllegalAction(f"{hex} is off the board")
        if self.board.is_planet(hex):
            raise IllegalAction(f"{hex} is a planet and cannot be charted")
        if hex in self._tiles:
            raise IllegalAction(f"{hex} is already charted")
        if len(exits) != 2:
            raise IllegalAction("A new tile must have exactly two exits")
        illegal = exits - self.legal_exits(hex)
        if illegal:
            raise IllegalAction(f"Exits {sorted(illegal)} face off the board")
        if not self._touches_network(hex, exits, reachable):
            raise IllegalAction(f"Tile at {hex} would not connect to {corp}'s network")

    def check_upgrade(
        self, corp: str, hex: Hex, new_exit: Direction, reachable: frozenset[Hex]
    ) -> None:
        tile = self._tiles.get(hex)
        if tile is None:
            raise IllegalAction(f"{hex} is not charted")
        if len(tile.exits) >= self.MAX_EXITS:
            raise IllegalAction(f"{hex} already has {self.MAX_EXITS} exits")
        if new_exit in tile.exits:
            raise IllegalAction(f"{hex} already has exit {new_exit.name}")
        if new_exit not in self.legal_exits(hex):
            raise IllegalAction(f"Exit {new_exit.name} at {hex} faces off the board")
        if hex not in reachable:
            raise IllegalAction(f"{corp} has no connected service at {hex}")

    def check_extend_service(self, corp: str, hex: Hex, reachable: frozenset[Hex]) -> None:
        tile = self._tiles.get(hex)
        if tile is None:
            raise IllegalAction(f"{hex} is not charted")
        if hex in self._service.get(corp, set()):
            raise IllegalAction(f"{corp} already has service at {hex}")
        if not self._touches_network(hex, tile.exits, reachable):
            raise IllegalAction(f"{hex} is not connected to {corp}'s network")

    def _touches_network(
        self, hex: Hex, exits: frozenset[Direction], reachable: frozenset[Hex]
    ) -> bool:
        for direction in exits:
            neighbor = hex.neighbor(direction)
            if neighbor in reachable and self.has_exit(neighbor, direction.opposite):
                return True
        return False

    # --- mutation (call check_* first, or use Game which does) ---------------

    def chart(
        self, corp: str, hex: Hex, exits: frozenset[Direction], reachable: frozenset[Hex]
    ) -> None:
        self.check_chart(corp, hex, exits, reachable)
        self._tiles[hex] = Tile(exits)
        self._service.setdefault(corp, set()).add(hex)

    def upgrade(self, corp: str, hex: Hex, new_exit: Direction, reachable: frozenset[Hex]) -> None:
        self.check_upgrade(corp, hex, new_exit, reachable)
        self._tiles[hex] = Tile(self._tiles[hex].exits | {new_exit})

    def extend_service(self, corp: str, hex: Hex, reachable: frozenset[Hex]) -> None:
        self.check_extend_service(corp, hex, reachable)
        self._service.setdefault(corp, set()).add(hex)
