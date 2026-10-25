"""Seeded placement of asteroid fields and nebulae.

Terrain is laid out once when a game starts, from the game seed alone, so a seed always
produces the same sky. Asteroid fields may never cut the planets into separate pieces.
"""

from __future__ import annotations

import random
from collections import deque

from bby18.board import Board, Terrain
from bby18.config import GameConfig
from bby18.hexgrid import Hex


def generate_terrain(board: Board, seed: int, config: GameConfig) -> dict[Hex, Terrain]:
    """Asteroid and nebula hexes for ``seed``, as a fraction of the board's space hexes."""
    space = board.space_hexes()
    rng = random.Random(f"terrain:{seed}")
    terrain: dict[Hex, Terrain] = {}
    for kind, fraction in (
        (Terrain.ASTEROID, config.asteroid_fraction),
        (Terrain.NEBULA, config.nebula_fraction),
    ):
        target = round(len(space) * fraction)
        _place(board, rng, terrain, kind, target, config.terrain_patch_size)
    return terrain


def _place(
    board: Board,
    rng: random.Random,
    terrain: dict[Hex, Terrain],
    kind: Terrain,
    target: int,
    patch_size: int,
) -> None:
    """Grow random patches of ``kind`` until ``target`` hexes are placed or nothing fits."""
    placed = 0
    free = [h for h in board.space_hexes() if h not in terrain]
    rng.shuffle(free)
    for start in free:
        if placed >= target:
            return
        if start in terrain or not _fits(board, terrain, kind, start):
            continue
        patch = [start]
        terrain[start] = kind
        wanted = min(rng.randint(1, patch_size), target - placed)
        while len(patch) < wanted:
            options = sorted(
                {
                    n
                    for h in patch
                    for _, n in h.neighbors()
                    if n in board.hexes
                    and not board.is_planet(n)
                    and n not in terrain
                    and _fits(board, terrain, kind, n)
                }
            )
            if not options:
                break
            chosen = rng.choice(options)
            terrain[chosen] = kind
            patch.append(chosen)
        placed += len(patch)


def _fits(board: Board, terrain: dict[Hex, Terrain], kind: Terrain, hex: Hex) -> bool:
    """Whether ``hex`` can take ``kind`` without isolating any planet."""
    if kind is not Terrain.ASTEROID:
        return True
    asteroids = {h for h, t in terrain.items() if t is Terrain.ASTEROID} | {hex}
    return planets_connected(board, asteroids)


def planets_connected(board: Board, asteroids: set[Hex]) -> bool:
    """Whether every planet can reach every other without crossing an asteroid hex."""
    start = board.planets[0].hex
    seen = {start}
    queue = deque([start])
    while queue:
        for _, n in queue.popleft().neighbors():
            if n in board.hexes and n not in asteroids and n not in seen:
                seen.add(n)
                queue.append(n)
    return all(p.hex in seen for p in board.planets)
