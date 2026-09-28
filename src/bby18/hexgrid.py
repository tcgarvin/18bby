"""Axial hex coordinates on a pointy-top grid.

Coordinates follow the map design doc: positive ``q`` points right, positive ``r`` points
down-right on the drawing.
"""

from __future__ import annotations

from enum import IntEnum
from typing import NamedTuple


class Direction(IntEnum):
    """The six exits of a pointy-top hex, clockwise from the right edge."""

    E = 0
    SE = 1
    SW = 2
    W = 3
    NW = 4
    NE = 5

    @property
    def opposite(self) -> Direction:
        return Direction((self + 3) % 6)

    @property
    def delta(self) -> tuple[int, int]:
        return _DELTAS[self]


_DELTAS: dict[Direction, tuple[int, int]] = {
    Direction.E: (1, 0),
    Direction.SE: (0, 1),
    Direction.SW: (-1, 1),
    Direction.W: (-1, 0),
    Direction.NW: (0, -1),
    Direction.NE: (1, -1),
}


class Hex(NamedTuple):
    q: int
    r: int

    def neighbor(self, direction: Direction) -> Hex:
        dq, dr = direction.delta
        return Hex(self.q + dq, self.r + dr)

    def neighbors(self) -> list[tuple[Direction, Hex]]:
        return [(d, self.neighbor(d)) for d in Direction]

    def direction_to(self, other: Hex) -> Direction:
        """Direction from this hex to an adjacent hex.

        Raises ValueError when the hexes are not adjacent.
        """
        delta = (other.q - self.q, other.r - self.r)
        for direction, d in _DELTAS.items():
            if d == delta:
                return direction
        raise ValueError(f"{other} is not adjacent to {self}")

    def distance(self, other: Hex) -> int:
        dq = other.q - self.q
        dr = other.r - self.r
        return max(abs(dq), abs(dr), abs(dq + dr))

    def __str__(self) -> str:
        return f"({self.q},{self.r})"


def hexes_within_radius(radius: int) -> list[Hex]:
    """Every hex with axial distance at most ``radius`` from the origin."""
    return [
        Hex(q, r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if max(abs(q), abs(r), abs(q + r)) <= radius
    ]
