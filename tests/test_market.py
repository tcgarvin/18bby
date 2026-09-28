"""The two-dimensional stock market and the rules that move prices on it."""

from dataclasses import replace

import pytest

from bby18.actions import BuyShare, PassStock, SellShares, ShareSource
from bby18.config import DEFAULT_CONFIG, GameConfig
from bby18.game import Game
from bby18.market import MarketCell, StockMarket
from bby18.revenue import RevenueResult
from bby18.session import GameSession
from bby18.state import Corporation

SMALL = replace(
    DEFAULT_CONFIG,
    stock_market=(
        (70, 80, 90, 100),
        (60, 70, 80),
        (50, 60),
    ),
    par_column=1,
    par_prices=(60, 70),
)


@pytest.fixture
def market() -> StockMarket:
    return StockMarket(SMALL)


def test_par_cells_are_found_in_the_par_column(market: StockMarket) -> None:
    assert market.par_cell(70) == MarketCell(1, 1)
    assert market.par_cell(60) == MarketCell(2, 1)


def test_par_price_missing_from_par_column_is_rejected() -> None:
    with pytest.raises(ValueError, match="Par prices"):
        StockMarket(replace(SMALL, par_prices=(60, 90)))


def test_right_moves_along_the_row_then_up_at_its_end(market: StockMarket) -> None:
    assert market.right(MarketCell(1, 1)) == MarketCell(1, 2)
    assert market.right(MarketCell(1, 1), 2) == MarketCell(0, 2)
    assert market.right(MarketCell(0, 3)) == MarketCell(0, 3)


def test_left_moves_along_the_row_then_down_at_the_edge(market: StockMarket) -> None:
    assert market.left(MarketCell(0, 1)) == MarketCell(0, 0)
    assert market.left(MarketCell(0, 0)) == MarketCell(1, 0)
    assert market.left(MarketCell(2, 0)) == MarketCell(2, 0)


def test_down_stops_where_the_row_below_is_shorter(market: StockMarket) -> None:
    assert market.down(MarketCell(0, 1), 5) == MarketCell(2, 1)
    assert market.down(MarketCell(1, 2)) == MarketCell(1, 2)


def test_up_stops_at_the_top_row(market: StockMarket) -> None:
    assert market.up(MarketCell(2, 1), 5) == MarketCell(0, 1)


def test_default_market_has_rows_below_every_par() -> None:
    market = StockMarket(DEFAULT_CONFIG)
    for par in DEFAULT_CONFIG.par_prices:
        cell = market.par_cell(par)
        assert market.price_at(market.down(cell)) < par


# --- rules that move the price ---------------------------------------------------------------


def new_game(config: GameConfig = DEFAULT_CONFIG) -> Game:
    return Game.new(["Ann", "Bo", "Cy"], config)


def float_cec(game: Game, par: int = 100) -> Corporation:
    ann, bo, cy = game.players
    game.apply_stock_action(ann, BuyShare("CEC", ShareSource.IPO, par), set())
    for player in (bo, cy, bo):
        game.apply_stock_action(player, BuyShare("CEC", ShareSource.IPO), set())
    corp = game.corp("CEC")
    assert corp.floated
    return corp


def fix_revenue(game: Game, total: int) -> None:
    game.revenue = lambda corp: RevenueResult((), floor=total)  # type: ignore[method-assign]


@pytest.mark.parametrize(
    ("revenue", "columns"),
    [(49, 0), (50, 1), (149, 1), (150, 2), (400, 2)],
)
def test_payout_moves_right_by_revenue_relative_to_price(revenue: int, columns: int) -> None:
    game = new_game()
    corp = float_cec(game, par=100)
    start = corp.market_cell
    fix_revenue(game, revenue)
    game.settle_revenue(corp, pay=True)
    assert corp.market_cell == game.market.right(start, columns)


def test_withholding_moves_left_one_column() -> None:
    game = new_game()
    corp = float_cec(game, par=100)
    start = corp.market_cell
    fix_revenue(game, 300)
    game.settle_revenue(corp, pay=False)
    assert corp.market_cell == MarketCell(start.row, start.col - 1)


def test_unheld_shares_pay_nobody() -> None:
    game = new_game()
    corp = float_cec(game, par=100)
    treasury, bank = corp.treasury, game.bank
    fix_revenue(game, 105)
    game.settle_revenue(corp, pay=True)
    assert corp.treasury == treasury
    held = sum(p.shares_in("CEC") for p in game.players)
    assert held == 5
    assert game.bank == bank - 10 * held


def test_selling_moves_down_one_row_per_share() -> None:
    game = new_game()
    corp = float_cec(game, par=80)
    game.stock_rounds_played = 1
    start = corp.market_cell
    game.apply_stock_action(game.players[1], BuyShare("CEC", ShareSource.IPO), set())
    game.apply_stock_action(game.players[1], SellShares("CEC", 2), set())
    assert corp.market_cell == game.market.down(start, 2)


def test_sold_out_corporation_moves_up_at_end_of_stock_round() -> None:
    game = new_game()
    corp = float_cec(game, par=80)
    start = corp.market_cell
    corp.ipo_shares = 0
    game.finish_stock_round()
    assert corp.market_cell == game.market.up(start)
    assert game.log[-1].text == f"is sold out; price {game.price(corp)}"


def test_corporation_with_shares_left_does_not_move_at_end_of_stock_round() -> None:
    game = new_game()
    corp = float_cec(game, par=80)
    start = corp.market_cell
    game.finish_stock_round()
    assert corp.market_cell == start
    assert game.stock_rounds_played == 1


def test_session_applies_sold_out_move_when_stock_round_ends() -> None:
    game = new_game()
    corp = float_cec(game, par=80)
    corp.ipo_shares = 0
    start = corp.market_cell
    session = GameSession(game, bots={})
    for _ in game.players:
        session.apply(PassStock())
    assert corp.market_cell == game.market.up(start)


def test_serializer_reports_market_cell_and_dividend_preview() -> None:
    from bby18.api.serialize import session_to_json

    game = new_game()
    corp = float_cec(game, par=100)
    fix_revenue(game, 150)
    state = session_to_json(GameSession(game, bots={}))
    cec = next(c for c in state["corporations"] if c["id"] == "CEC")
    cell = corp.market_cell
    assert cec["marketCell"] == [cell.row, cell.col]
    assert cec["dividendPreview"] == {
        "pay": game.market.price_at(game.market.right(cell, 2)),
        "withhold": game.market.price_at(game.market.left(cell)),
    }
    assert state["stockMarket"][cell.row][cell.col] == 100
