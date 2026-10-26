from dataclasses import replace

from bby18.board import Terrain
from bby18.config import CLASSIC_CONFIG
from bby18.game import Game, LogEntry
from bby18.hexgrid import Direction as D
from bby18.hexgrid import Hex
from bby18.metrics import count_log, frontier_costs, near_pair_links, planet_metrics
from bby18.network import HyperspaceNetwork
from bby18.state import CorpStatus

CLEAR = replace(CLASSIC_CONFIG, asteroid_fraction=0.0, nebula_fraction=0.0)


def _game(terrain: dict[Hex, Terrain]) -> Game:
    game = Game.new(["Ann", "Bo", "Cy"], CLEAR)
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


def test_planet_value_splits_each_pair_between_its_planets():
    game = _game({})
    _float(game)
    cec = game.corp("CEC")
    # Corellia (I/S) at (-5,3) to Alderaan (M) at (-4,1) via (-4,2): an industry-market pair.
    game.network.chart("CEC", Hex(-4, 2), frozenset({D.SW, D.NW}), game.reachable(cec))
    metrics = planet_metrics(game)
    assert metrics["Corellia"].reached_by == metrics["Alderaan"].reached_by == 1
    assert metrics["Corellia"].value == metrics["Alderaan"].value == 15
    assert metrics["Coruscant"].reached_by == 0 and metrics["Coruscant"].value == 0
    assert sum(m.value for m in metrics.values()) == game.revenue(cec).total


def test_frontier_cost_prices_nebulae_and_goes_around_asteroids():
    corellia = (-5, 3)
    cases = {
        "open": ({}, 60),
        "nebula": ({Hex(-4, 2): Terrain.NEBULA, Hex(-4, 3): Terrain.NEBULA}, 90),
        "one asteroid": ({Hex(-4, 2): Terrain.ASTEROID}, 60),
    }
    for terrain, expected in (v for v in cases.values()):
        game = _game(terrain)
        _float(game)
        reach = game.reachable(game.corp("CEC"))
        assert reach == {Hex(*corellia)}
        assert frontier_costs(game, "CEC", reach)["Kuat"] == expected


def test_frontier_cost_detours_when_both_short_routes_are_blocked():
    walled = {Hex(-4, 2): Terrain.ASTEROID, Hex(-4, 3): Terrain.ASTEROID}
    game = _game(walled)
    _float(game)
    reach = game.reachable(game.corp("CEC"))
    assert frontier_costs(game, "CEC", reach)["Kuat"] > 60


def test_near_pairs_are_all_stranded_before_anything_floats():
    game = _game({})
    total, linked, stranded = near_pair_links(game)
    assert total > 0 and linked == 0 and stranded == total


def test_count_log_prices_nebula_charts():
    log = [
        LogEntry("OR1.1", "CEC", "chart (-4,2) exits E/SW for 50"),
        LogEntry("OR1.1", "CEC", "chart (-4,3) exits E/W for 80"),
        LogEntry("OR1.2", "CEC", "upgrade (-4,3) add NE for 70"),
    ]
    corp = count_log(log, ["CEC"], top_price=400, chart_cost=50).corps["CEC"]
    assert (corp.charts, corp.nebula_charts, corp.chart_spend, corp.upgrades) == (2, 1, 130, 1)
