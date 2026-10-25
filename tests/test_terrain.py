from dataclasses import replace

import pytest

from bby18.actions import Chart, ExtendService, Upgrade
from bby18.board import Terrain, load_board
from bby18.config import DEFAULT_CONFIG
from bby18.game import Game
from bby18.hexgrid import Direction as D
from bby18.hexgrid import Hex
from bby18.network import HyperspaceNetwork, IllegalAction
from bby18.state import CorpStatus
from bby18.terrain import generate_terrain, planets_connected

CFG = DEFAULT_CONFIG


def _board_with(terrain: dict[Hex, Terrain]):
    return load_board().with_terrain(terrain)


def test_terrain_is_deterministic_from_the_seed():
    board = load_board()
    assert generate_terrain(board, 7, CFG) == generate_terrain(board, 7, CFG)
    assert generate_terrain(board, 7, CFG) != generate_terrain(board, 8, CFG)


def test_terrain_covers_the_configured_fraction_of_space_hexes():
    board = load_board()
    space = len(board.space_hexes())
    for seed in range(20):
        terrain = generate_terrain(board, seed, CFG)
        kinds = list(terrain.values())
        assert kinds.count(Terrain.ASTEROID) == round(space * CFG.asteroid_fraction)
        assert kinds.count(Terrain.NEBULA) == round(space * CFG.nebula_fraction)


def test_terrain_never_lands_on_planets_or_off_board():
    board = load_board()
    for seed in range(20):
        for hex in generate_terrain(board, seed, CFG):
            assert board.contains(hex) and not board.is_planet(hex)


def test_asteroids_never_split_the_planets():
    board = load_board()
    for seed in range(50):
        terrain = generate_terrain(board, seed, CFG)
        asteroids = {h for h, t in terrain.items() if t is Terrain.ASTEROID}
        assert planets_connected(board, asteroids)


def test_dense_asteroids_stop_short_rather_than_isolate_a_planet():
    greedy = replace(CFG, asteroid_fraction=0.9, nebula_fraction=0.0)
    board = load_board()
    terrain = generate_terrain(board, 3, greedy)
    asteroids = {h for h, t in terrain.items() if t is Terrain.ASTEROID}
    assert planets_connected(board, asteroids)
    assert len(asteroids) < round(len(board.space_hexes()) * 0.9)


def test_no_terrain_when_both_fractions_are_zero():
    clear = replace(CFG, asteroid_fraction=0.0, nebula_fraction=0.0)
    assert generate_terrain(load_board(), 1, clear) == {}


def test_patch_size_one_scatters_single_hexes():
    scattered = replace(CFG, terrain_patch_size=1)
    board = load_board()
    terrain = generate_terrain(board, 4, scattered)
    asteroids = {h for h, t in terrain.items() if t is Terrain.ASTEROID}
    assert len(asteroids) == round(len(board.space_hexes()) * CFG.asteroid_fraction)


def test_board_rejects_terrain_on_a_planet_or_off_board():
    base = load_board()
    planet = base.planets[0].hex
    with pytest.raises(ValueError):
        base.with_terrain({planet: Terrain.NEBULA})
    with pytest.raises(ValueError):
        base.with_terrain({Hex(99, 99): Terrain.ASTEROID})


def test_asteroid_hexes_are_not_neighbors_and_not_legal_exits():
    asteroid = Hex(-4, 2)
    board = _board_with({asteroid: Terrain.ASTEROID})
    corellia = board.planet_named("Corellia").hex
    assert asteroid not in [n for _, n in board.neighbors(corellia)]
    direction = corellia.direction_to(asteroid)
    assert direction not in board.on_board_directions(corellia)


def test_asteroid_cannot_be_charted():
    asteroid = Hex(-4, 2)
    net = HyperspaceNetwork(_board_with({asteroid: Terrain.ASTEROID}))
    corellia = net.board.planet_named("Corellia").hex
    with pytest.raises(IllegalAction, match="asteroid"):
        net.check_chart("CEC", asteroid, frozenset({D.E, D.W}), frozenset({corellia}))


def test_tile_cannot_have_an_exit_facing_an_asteroid():
    asteroid = Hex(-4, 3)
    net = HyperspaceNetwork(_board_with({asteroid: Terrain.ASTEROID}))
    hex = Hex(-3, 3)
    facing = hex.direction_to(asteroid)
    assert facing not in net.legal_exits(hex)


def _game_with(terrain: dict[Hex, Terrain]) -> Game:
    clear = replace(CFG, asteroid_fraction=0.0, nebula_fraction=0.0)
    game = Game.new(["Ann", "Bo", "Cy"], clear)
    game.board = game.board.with_terrain(terrain)
    game.network = HyperspaceNetwork(game.board)
    return game


def _float(game: Game, corp_id: str = "CEC") -> None:
    corp = game.corp(corp_id)
    corp.status = CorpStatus.FLOATED
    corp.par = 60
    corp.market_cell = game.market.par_cell(60)
    corp.treasury = 480
    corp.president = "P1"


def test_nebula_chart_costs_the_surcharge_and_is_offered_at_that_price():
    nebula = Hex(-4, 2)
    game = _game_with({nebula: Terrain.NEBULA})
    _float(game)
    cec = game.corp("CEC")
    charts = [a for a in game.legal_network_actions(cec) if isinstance(a, Chart)]
    in_nebula = [a for a in charts if a.hex == nebula]
    elsewhere = [a for a in charts if a.hex != nebula]
    assert in_nebula and all(a.cost == 50 + 30 for a in in_nebula)
    assert elsewhere and all(a.cost == 50 for a in elsewhere)
    game.apply_network_action(cec, in_nebula[0])
    assert cec.treasury == 480 - 80


def test_extending_service_onto_a_nebula_costs_the_usual_amount():
    nebula = Hex(-4, 2)
    game = _game_with({nebula: Terrain.NEBULA})
    _float(game, "CEC")
    _float(game, "KDY")
    cec, kdy = game.corp("CEC"), game.corp("KDY")
    game.network.chart("KDY", nebula, frozenset({D.E, D.SW}), game.reachable(kdy))
    service = [a for a in game.legal_network_actions(cec) if isinstance(a, ExtendService)]
    assert [a.cost for a in service if a.hex == nebula] == [50]


def test_nebula_tile_can_never_be_upgraded():
    nebula = Hex(-4, 2)
    game = _game_with({nebula: Terrain.NEBULA})
    _float(game)
    cec = game.corp("CEC")
    game.network.chart("CEC", nebula, frozenset({D.SW, D.NW}), game.reachable(cec))
    assert not [a for a in game.legal_network_actions(cec) if isinstance(a, Upgrade)]
    with pytest.raises(IllegalAction, match="nebula"):
        game.network.check_upgrade("CEC", nebula, D.E, game.reachable(cec))


def test_open_space_tile_upgrades_at_the_expansion_cost():
    game = _game_with({})
    _float(game)
    cec = game.corp("CEC")
    hex = Hex(-4, 2)
    game.network.chart("CEC", hex, frozenset({D.SW, D.NW}), game.reachable(cec))
    upgrades = [a for a in game.legal_network_actions(cec) if isinstance(a, Upgrade)]
    assert upgrades and all(a.cost == CFG.upgrade_cost == 70 for a in upgrades)
    game.apply_network_action(cec, upgrades[0])
    assert cec.treasury == 480 - 70


def test_games_with_the_same_seed_share_a_sky_and_different_seeds_do_not():
    names = ["Ann", "Bo", "Cy"]
    assert Game.new(names, CFG, 5).board.terrain == Game.new(names, CFG, 5).board.terrain
    assert Game.new(names, CFG, 5).board.terrain != Game.new(names, CFG, 6).board.terrain
