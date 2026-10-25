from dataclasses import replace

from bby18.board import Terrain, load_board
from bby18.config import DEFAULT_CONFIG
from bby18.hexgrid import Hex
from bby18.terrain_report import pair_costs, terrain_report


def test_planets_two_hexes_apart_link_for_one_chart():
    costs = pair_costs(load_board(), DEFAULT_CONFIG)
    # Corellia (-5,3) and Kuat (-3,2) have one hex between them on either of two routes.
    assert costs[("Corellia", "Kuat")] == DEFAULT_CONFIG.chart_cost


def test_nebula_and_asteroids_change_pair_costs():
    board = load_board()
    both = {Hex(-4, 2): Terrain.NEBULA, Hex(-4, 3): Terrain.NEBULA}
    nebula_cost = pair_costs(board.with_terrain(both), DEFAULT_CONFIG)[("Corellia", "Kuat")]
    assert nebula_cost == DEFAULT_CONFIG.chart_cost + DEFAULT_CONFIG.nebula_chart_surcharge
    walled = {Hex(-4, 2): Terrain.ASTEROID, Hex(-4, 3): Terrain.ASTEROID}
    walled_cost = pair_costs(board.with_terrain(walled), DEFAULT_CONFIG)[("Corellia", "Kuat")]
    assert walled_cost > DEFAULT_CONFIG.chart_cost


def test_empty_sky_changes_nothing():
    clear = replace(DEFAULT_CONFIG, asteroid_fraction=0.0, nebula_fraction=0.0)
    report = terrain_report(range(1, 4), clear)
    assert report["share_of_cheap_pairs_made_costlier"] == 0
    assert report["mean_extra_cost_per_cheap_pair"] == 0
