import pytest

from bby18.board import load_board
from bby18.hexgrid import Direction as D
from bby18.hexgrid import Hex
from bby18.network import HyperspaceNetwork, IllegalAction


@pytest.fixture
def board():
    return load_board()


@pytest.fixture
def net(board):
    return HyperspaceNetwork(board)


CORELLIA = Hex(-5, 3)
KUAT = Hex(-3, 2)
KASHYYYK = Hex(0, 0)


def build_design_doc_example(net):
    """The illustrated Corellia/Kuat -> Kashyyyk network from the map design doc."""
    reach = net.reachable("A", CORELLIA)
    net.chart("A", Hex(-4, 2), frozenset({D.SW, D.NE}), reach)
    reach = net.reachable("A", CORELLIA)
    net.chart("A", Hex(-3, 1), frozenset({D.SW, D.E}), reach)
    reach = net.reachable("A", CORELLIA)
    net.chart("A", Hex(-2, 1), frozenset({D.W, D.E}), reach)
    reach = net.reachable("A", CORELLIA)
    net.chart("A", Hex(-1, 1), frozenset({D.W, D.NE}), reach)


def test_charting_from_homeworld_reaches_kashyyyk(net):
    build_design_doc_example(net)
    reach = net.reachable("A", CORELLIA)
    assert KASHYYYK in reach
    assert Hex(-3, 1) in reach
    assert KUAT not in reach


def test_first_chart_requires_connection_to_network(net):
    with pytest.raises(IllegalAction):
        net.chart("A", Hex(-3, 1), frozenset({D.SW, D.E}), net.reachable("A", CORELLIA))


def test_exit_must_face_the_network_not_just_be_adjacent(net):
    # Tile adjacent to Corellia but with exits pointing elsewhere.
    with pytest.raises(IllegalAction):
        net.chart("A", Hex(-4, 2), frozenset({D.E, D.NE}), net.reachable("A", CORELLIA))


def test_cannot_chart_planet_or_off_board(net):
    reach = net.reachable("A", CORELLIA)
    with pytest.raises(IllegalAction):
        net.chart("A", CORELLIA, frozenset({D.E, D.W}), reach)
    with pytest.raises(IllegalAction):
        net.chart("A", Hex(-6, 4), frozenset({D.W, D.NE}), reach)


def test_upgrade_adds_junction_and_service_extension_shares_it(net):
    build_design_doc_example(net)
    # B at Kuat cannot reach the junction before the upgrade.
    assert Hex(-3, 1) not in net.reachable("B", KUAT)
    net.upgrade("A", Hex(-3, 1), D.SE, net.reachable("A", CORELLIA))
    assert net.tile_at(Hex(-3, 1)).exits == {D.SW, D.E, D.SE}
    # Still no service for B, so still unreachable.
    assert Hex(-3, 1) not in net.reachable("B", KUAT)
    for h in (Hex(-3, 1), Hex(-2, 1), Hex(-1, 1)):
        net.extend_service("B", h, net.reachable("B", KUAT))
    assert KASHYYYK in net.reachable("B", KUAT)
    assert net.corporations_serving(Hex(-2, 1)) == {"A", "B"}
    assert net.corporations_serving(Hex(-4, 2)) == {"A"}
    # A's own network is unaffected and now also reaches Kuat through the junction.
    assert KUAT in net.reachable("A", CORELLIA)


def test_upgrade_requires_service_and_caps_at_three_exits(net):
    build_design_doc_example(net)
    with pytest.raises(IllegalAction):
        net.upgrade("B", Hex(-3, 1), D.SE, net.reachable("B", KUAT))
    net.upgrade("A", Hex(-3, 1), D.SE, net.reachable("A", CORELLIA))
    with pytest.raises(IllegalAction):
        net.upgrade("A", Hex(-3, 1), D.NW, net.reachable("A", CORELLIA))


def test_service_extension_must_connect(net):
    build_design_doc_example(net)
    with pytest.raises(IllegalAction):
        net.extend_service("B", Hex(-1, 1), net.reachable("B", KUAT))


def test_planets_are_pass_through_hubs(net):
    build_design_doc_example(net)
    # Chart onward from Kashyyyk: the planet hex needs no tile.
    net.chart("A", Hex(1, 0), frozenset({D.W, D.E}), net.reachable("A", CORELLIA))
    assert Hex(1, 0) in net.reachable("A", CORELLIA)
