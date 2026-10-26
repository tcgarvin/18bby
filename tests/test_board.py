import pytest

from bby18.board import board_from_json, load_board
from bby18.config import CLASSIC_CONFIG
from bby18.hexgrid import Hex, hexes_within_radius


@pytest.fixture(scope="module")
def board():
    return load_board()


def test_planet_counts_by_region(board):
    counts = {}
    for p in board.planets:
        counts[p.region] = counts.get(p.region, 0) + 1
    assert counts == {"Core": 6, "Mid Rim": 8, "Outer Rim": 10}
    assert len(board.space_hexes()) == 93


def test_dual_tags_are_split(board):
    assert board.planet_named("Corellia").tags == {"I", "S"}
    assert board.planet_named("Naboo").tags == {"A", "R"}
    assert board.planet_named("Kuat").tags == {"S"}


def test_kashyyyk_is_at_origin(board):
    assert board.planet_at(Hex(0, 0)).name == "Kashyyyk"
    assert not board.is_planet(Hex(0, 1))


def test_no_two_planets_adjacent(board):
    for a in board.planets:
        for b in board.planets:
            if a is not b:
                assert a.hex.distance(b.hex) >= 2


def test_nothing_lies_east_of_ryloth(board):
    ryloth = board.planet_named("Ryloth").hex
    assert len(board.hexes) == 117
    assert max(2 * h.q + h.r for h in board.hexes) == 2 * ryloth.q + ryloth.r


def test_classic_rules_keep_the_full_hexagon():
    classic = load_board(CLASSIC_CONFIG.map_file)
    assert classic.hexes == frozenset(hexes_within_radius(6))
    assert [p.hex for p in classic.planets] == [p.hex for p in load_board().planets]


def test_map_cells_outside_the_radius_are_rejected():
    data = {"map": {"radius": 1, "cells": [[0, 0], [2, 0]], "planets": []}}
    with pytest.raises(ValueError, match="outside the stated radius"):
        board_from_json(data)
