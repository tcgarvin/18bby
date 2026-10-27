"""The shared hyperspace network and each corporation's service layer.

Charted tiles are shared geometry. Service is per corporation. Planets are open hubs:
they have every exit and never need charting or service.

Under the experimental facility rules a planet's exits are limited instead (``limit_planet_exits``)
and have no direction until a lane claims one: charting or upgrading a tile with an exit facing
the planet claims an unclaimed exit for that side, and the planet connects only through claimed
sides. A lane facing a planet with no unclaimed exit dangles until a new exit is given to it.
The construction site is never limited.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from bby18.board import Board, Terrain
from bby18.hexgrid import Direction, Hex

_OPPOSITE: dict[Direction, Direction] = {d: d.opposite for d in Direction}
_ALL_SIDES: frozenset[Direction] = frozenset(Direction)
"""The sides an open hub connects through: every one."""


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

    def __init__(self, board: Board, reserved: frozenset[Hex] = frozenset()) -> None:
        self.board = board
        self.reserved = reserved
        """Space hexes that may not be charted yet, though tiles may point at them (the future
        Death Star construction site)."""
        self._tiles: dict[Hex, Tile] = {}
        self._service: dict[str, set[Hex]] = {}
        self._planet_exits: dict[Hex, int] = {}
        """Exits of each exit-limited planet (facility rules). Planets not listed are open hubs."""
        self._claimed: dict[Hex, frozenset[Direction]] = {}
        """Sides of each exit-limited planet that lanes have claimed; it connects only there."""

    def copy(self) -> HyperspaceNetwork:
        """A cheap copy sharing the immutable board, for what-if evaluation."""
        clone = HyperspaceNetwork(self.board, self.reserved)
        clone._tiles = dict(self._tiles)
        clone._service = {c: set(h) for c, h in self._service.items()}
        clone._planet_exits = dict(self._planet_exits)
        clone._claimed = dict(self._claimed)
        return clone

    def rebase(self, board: Board, reserved: frozenset[Hex]) -> None:
        """Lay the existing tiles and service over ``board``, the same geometry with planets
        added or removed (the Death Star site arriving or leaving). Tiles stay as they are, so
        a tile pointing into a hex that stops being a planet now leads nowhere."""
        if board.hexes != self.board.hexes:
            raise ValueError("A network can only move to a board with the same hexes")
        clashes = sorted(h for h in self._tiles if board.is_planet(h))
        if clashes:
            raise ValueError(f"Charted hexes {clashes} cannot become planets")
        vanished = sorted(h for h in self._planet_exits if not board.is_planet(h))
        if vanished:
            raise ValueError(f"Exit-limited planets {vanished} cannot become space")
        self.board = board
        self.reserved = reserved

    def remove_service(self, corp: str) -> None:
        """Drop all of ``corp``'s service. Its tiles stay charted for everyone else."""
        self._service.pop(corp, None)

    def limit_planet_exits(self, planets: Iterable[Hex], exits: int) -> None:
        """Give each of ``planets`` ``exits`` unclaimed exits instead of every exit (the facility
        rules). Call it before anything is charted, so that no lane faces a planet unclaimed."""
        if self._tiles:
            raise ValueError("Planet exits must be limited before any tile is charted")
        for hex in planets:
            if not self.board.is_planet(hex):
                raise ValueError(f"{hex} is not a planet")
            if hex in self._planet_exits:
                raise ValueError(f"The exits of {hex} are already limited")
            self._planet_exits[hex] = exits
            self._claimed[hex] = frozenset()

    def add_planet_exit(self, hex: Hex) -> None:
        """One more unclaimed exit on exit-limited planet ``hex`` (a facility was built there)."""
        if hex not in self._planet_exits:
            raise IllegalAction(f"{hex} is not a planet with limited exits")
        self._planet_exits[hex] += 1

    def claim_exit(self, hex: Hex, side: Direction) -> None:
        """Give one of exit-limited planet ``hex``'s unclaimed exits to the dangling lane on
        ``side`` (see ``dangling_sides``)."""
        if self.unclaimed_exits(hex) < 1:
            raise IllegalAction(f"{hex} has no unclaimed exit")
        if side not in self.dangling_sides(hex):
            raise IllegalAction(f"No lane dangles at {hex} on side {side.name}")
        self._claimed[hex] = self._claimed[hex] | {side}

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
        """Whether ``hex`` can carry traffic out of ``direction``. Open hubs always can; an
        exit-limited planet only on its claimed sides."""
        if self.board.is_planet(hex):
            return direction in self._claimed.get(hex, _ALL_SIDES)
        tile = self._tiles.get(hex)
        return tile is not None and direction in tile.exits

    def has_exit_limit(self, hex: Hex) -> bool:
        """Whether ``hex`` is a planet with limited exits (facility rules)."""
        return hex in self._planet_exits

    def planet_exits(self, hex: Hex) -> int:
        """How many exits exit-limited planet ``hex`` has, claimed or not."""
        if hex not in self._planet_exits:
            raise KeyError(f"{hex} is not a planet with limited exits")
        return self._planet_exits[hex]

    def claimed_exits(self, hex: Hex) -> frozenset[Direction]:
        """The sides of exit-limited planet ``hex`` that lanes have claimed."""
        if hex not in self._claimed:
            raise KeyError(f"{hex} is not a planet with limited exits")
        return self._claimed[hex]

    def unclaimed_exits(self, hex: Hex) -> int:
        """Exits of exit-limited planet ``hex`` that no lane has claimed yet; 0 for any other
        hex (an open hub's exits need no claiming)."""
        if hex not in self._planet_exits:
            return 0
        return self._planet_exits[hex] - len(self._claimed[hex])

    def dangling_sides(self, hex: Hex) -> frozenset[Direction]:
        """Sides of exit-limited planet ``hex`` facing a charted tile (anyone's) with an exit
        toward it that the planet has not claimed: lanes that dangle there."""
        claimed = self.claimed_exits(hex)
        sides = set()
        for direction, neighbor in self.board.neighbors(hex):
            if direction in claimed:
                continue
            tile = self._tiles.get(neighbor)
            if tile is not None and _OPPOSITE[direction] in tile.exits:
                sides.add(direction)
        return frozenset(sides)

    def connected(self, a: Hex, b: Hex) -> bool:
        """Adjacent hexes are connected when each has an exit facing the other. Two hubs
        (planets, or a planet and the Death Star site) never connect directly: traffic between
        them needs at least one charted lane."""
        if self.board.is_planet(a) and self.board.is_planet(b):
            return False
        direction = a.direction_to(b)
        return self.has_exit(a, direction) and self.has_exit(b, direction.opposite)

    def reachable(self, corp: str, origin: Hex) -> frozenset[Hex]:
        """All hexes ``corp`` can reach from ``origin`` through its own service. Adjacent hubs
        do not connect directly (see ``connected``)."""
        service = self._service.get(corp, set())
        board = self.board
        seen = {origin}
        queue = deque([origin])
        while queue:
            current = queue.popleft()
            for direction, nxt in board.neighbors(current):
                if nxt in seen:
                    continue
                if board.is_planet(nxt):
                    if board.is_planet(current):
                        continue
                elif nxt not in service:
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
        if self.board.terrain_at(hex) is Terrain.ASTEROID:
            raise IllegalAction(f"{hex} is an asteroid field and cannot be charted")
        if hex in self._tiles:
            raise IllegalAction(f"{hex} is already charted")
        if hex in self.reserved:
            raise IllegalAction(f"{hex} is reserved for the Death Star and cannot be charted")
        if len(exits) != 2:
            raise IllegalAction("A new tile must have exactly two exits")
        illegal = exits - self.legal_exits(hex)
        if illegal:
            raise IllegalAction(f"Exits {sorted(illegal)} face off the board")
        if not self._touches_network(hex, exits, reachable, claiming=True):
            raise IllegalAction(f"Tile at {hex} would not connect to {corp}'s network")

    def check_upgrade(
        self, corp: str, hex: Hex, new_exit: Direction, reachable: frozenset[Hex]
    ) -> None:
        tile = self._tiles.get(hex)
        if tile is None:
            raise IllegalAction(f"{hex} is not charted")
        if len(tile.exits) >= self.MAX_EXITS:
            raise IllegalAction(f"{hex} already has {self.MAX_EXITS} exits")
        if self.board.terrain_at(hex) is Terrain.NEBULA:
            raise IllegalAction(f"{hex} is a nebula and cannot be upgraded")
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
        # Extending service claims nothing, so only lanes already connected count.
        if not self._touches_network(hex, tile.exits, reachable, claiming=False):
            raise IllegalAction(f"{hex} is not connected to {corp}'s network")

    def _touches_network(
        self,
        hex: Hex,
        exits: frozenset[Direction],
        reachable: frozenset[Hex],
        *,
        claiming: bool,
    ) -> bool:
        """Whether a tile at ``hex`` with ``exits`` connects to a hex in ``reachable``. When
        ``claiming`` (a new tile), a reached planet with an unclaimed exit connects on any side,
        since the tile would claim it."""
        for direction in exits:
            neighbor = hex.neighbor(direction)
            if neighbor not in reachable:
                continue
            if self.has_exit(neighbor, direction.opposite):
                return True
            if claiming and self.unclaimed_exits(neighbor) > 0:
                return True
        return False

    def _claim_facing(self, hex: Hex, exits: Iterable[Direction]) -> frozenset[Hex]:
        """Claim, for the tile at ``hex``, an exit of each exit-limited planet one of ``exits``
        faces that still has an unclaimed one. Returns the planets claimed."""
        claimed = set()
        for direction in sorted(exits):
            neighbor = hex.neighbor(direction)
            if self.unclaimed_exits(neighbor) > 0:
                self._claimed[neighbor] = self._claimed[neighbor] | {_OPPOSITE[direction]}
                claimed.add(neighbor)
        return frozenset(claimed)

    # --- mutation (call check_* first, or use Game which does) ---------------

    def chart(
        self, corp: str, hex: Hex, exits: frozenset[Direction], reachable: frozenset[Hex]
    ) -> frozenset[Hex]:
        """Chart a tile and give ``corp`` service on it. Returns the exit-limited planets whose
        exit it claimed."""
        self.check_chart(corp, hex, exits, reachable)
        self._tiles[hex] = Tile(exits)
        self._service.setdefault(corp, set()).add(hex)
        return self._claim_facing(hex, exits)

    def upgrade(
        self, corp: str, hex: Hex, new_exit: Direction, reachable: frozenset[Hex]
    ) -> frozenset[Hex]:
        """Add ``new_exit`` to a tile. Returns the exit-limited planet whose exit the new exit
        claimed, if any; the tile's older exits claim nothing."""
        self.check_upgrade(corp, hex, new_exit, reachable)
        self._tiles[hex] = Tile(self._tiles[hex].exits | {new_exit})
        return self._claim_facing(hex, (new_exit,))

    def extend_service(self, corp: str, hex: Hex, reachable: frozenset[Hex]) -> None:
        self.check_extend_service(corp, hex, reachable)
        self._service.setdefault(corp, set()).add(hex)
