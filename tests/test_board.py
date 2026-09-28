import pytest

from bby18.board import load_board
from bby18.hexgrid import Hex


@pytest.fixture(scope="module")
def board():
    return load_board()


def test_planet_counts_by_region(board):
    counts = {}
    for p in board.planets:
        counts[p.region] = counts.get(p.region, 0) + 1
    assert counts == {"Core": 6, "Mid Rim": 8, "Outer Rim": 10}
    assert len(board.space_hexes()) == 103


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
