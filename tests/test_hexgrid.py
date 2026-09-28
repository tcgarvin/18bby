from bby18.hexgrid import Direction, Hex, hexes_within_radius


def test_board_of_radius_six_has_127_hexes():
    assert len(hexes_within_radius(6)) == 127


def test_neighbor_deltas_match_design_doc():
    origin = Hex(0, 0)
    assert origin.neighbor(Direction.E) == Hex(1, 0)
    assert origin.neighbor(Direction.SE) == Hex(0, 1)
    assert origin.neighbor(Direction.SW) == Hex(-1, 1)
    assert origin.neighbor(Direction.W) == Hex(-1, 0)
    assert origin.neighbor(Direction.NW) == Hex(0, -1)
    assert origin.neighbor(Direction.NE) == Hex(1, -1)


def test_opposite_directions_round_trip():
    for d in Direction:
        assert Hex(2, -1).neighbor(d).neighbor(d.opposite) == Hex(2, -1)


def test_direction_to_adjacent_and_error_for_distant():
    assert Hex(-5, 3).direction_to(Hex(-4, 2)) == Direction.NE
    try:
        Hex(0, 0).direction_to(Hex(2, 0))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_distance_matches_design_doc_formula():
    assert Hex(-5, 3).distance(Hex(0, 0)) == 5
    assert Hex(-6, 0).distance(Hex(6, -6)) == 12
