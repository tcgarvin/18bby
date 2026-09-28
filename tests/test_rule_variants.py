"""Experimental rule variants behind GameConfig fields; the defaults are the current rules."""

from dataclasses import replace

import pytest

from bby18.actions import BuyShare, ShareSource
from bby18.api.serialize import session_to_json
from bby18.config import DEFAULT_CONFIG, GameConfig
from bby18.game import Game
from bby18.market import MarketCell
from bby18.playtest import play_one
from bby18.revenue import RevenueResult
from bby18.session import GameSession
from bby18.state import Corporation
from bby18.sweep import variant


def new_game(**overrides: object) -> Game:
    return Game.new(["Ann", "Bo", "Cy"], replace(DEFAULT_CONFIG, **overrides))


def buy(game: Game, player_index: int, corp_id: str, par: int = 0) -> None:
    game.apply_stock_action(
        game.players[player_index], BuyShare(corp_id, ShareSource.IPO, par), set()
    )


def float_corp(game: Game, corp_id: str = "CEC", par: int = 100) -> Corporation:
    buy(game, 0, corp_id, par=par)
    buy(game, 1, corp_id)
    buy(game, 2, corp_id)
    buy(game, 1, corp_id)
    corp = game.corp(corp_id)
    assert corp.floated
    return corp


def move_to_price(game: Game, corp: Corporation, price: int) -> None:
    """Put ``corp`` on the first market cell showing ``price``."""
    for row_index, row in enumerate(game.market.rows):
        if price in row:
            corp.market_cell = MarketCell(row_index, row.index(price))
            return
    raise ValueError(f"No market cell shows {price}")


def fix_revenue(game: Game, total: int) -> None:
    """Make every corporation earn exactly ``total`` (an empty matching with that floor)."""
    game.revenue = lambda corp: RevenueResult((), floor=total)  # type: ignore[method-assign]


def total_money(game: Game) -> int:
    """Player cash plus treasuries plus bank; the bank counter nets out every transfer."""
    cash = sum(p.cash for p in game.players)
    treasuries = sum(c.treasury for c in game.corporations.values())
    return cash + treasuries + game.bank


# --- validation --------------------------------------------------------------------------


@pytest.mark.parametrize("field_name", ["ipo_price_rule", "capitalization"], ids=str)
def test_unknown_rule_names_are_rejected_at_game_creation(field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        new_game(**{field_name: "bogus"})


def test_negative_income_floor_is_rejected() -> None:
    with pytest.raises(ValueError):
        new_game(homeworld_basic_income=-1)


# --- zero_revenue_moves_price -------------------------------------------------------------


def test_zero_revenue_leaves_price_when_disabled() -> None:
    game = new_game(zero_revenue_moves_price=False)
    corp = float_corp(game, par=100)
    start = corp.market_cell
    fix_revenue(game, 0)
    game.settle_revenue(corp, pay=True)
    assert corp.market_cell == start
    assert game.log[-1].text == "withholds 0; price 100"


def test_zero_revenue_drops_price_by_default() -> None:
    game = new_game()
    corp = float_corp(game, par=100)
    start = corp.market_cell
    fix_revenue(game, 0)
    game.settle_revenue(corp, pay=True)
    assert corp.market_cell == game.market.left(start)


def test_withholding_positive_revenue_still_drops_price_when_zero_rule_disabled() -> None:
    game = new_game(zero_revenue_moves_price=False)
    corp = float_corp(game, par=100)
    start = corp.market_cell
    fix_revenue(game, 40)
    game.settle_revenue(corp, pay=False)
    assert corp.market_cell == game.market.left(start)


# --- ipo_price_rule --------------------------------------------------------------------------


def test_ipo_price_is_par_before_float_under_market_rule() -> None:
    game = new_game(ipo_price_rule="market_after_float")
    buy(game, 0, "CEC", par=100)
    corp = game.corp("CEC")
    move_to_price(game, corp, 150)
    assert game.ipo_price(corp) == 100


def test_ipo_price_follows_market_after_float() -> None:
    game = new_game(ipo_price_rule="market_after_float")
    corp = float_corp(game, par=100)
    move_to_price(game, corp, 150)
    assert game.ipo_price(corp) == 150
    move_to_price(game, corp, 80)
    assert game.ipo_price(corp) == 100


def test_ipo_buy_after_float_charges_market_price_to_the_bank() -> None:
    game = new_game(ipo_price_rule="market_after_float")
    corp = float_corp(game, par=100)
    move_to_price(game, corp, 150)
    cy = game.players[2]
    cash, bank, treasury = cy.cash, game.bank, corp.treasury
    buy(game, 2, "CEC")
    assert cy.cash == cash - 150
    assert game.bank == bank + 150
    assert corp.treasury == treasury
    assert game.log[-1].text == "buys CEC from ipo for 150"


def test_ipo_buy_is_illegal_when_player_cannot_cover_market_price() -> None:
    game = new_game(ipo_price_rule="market_after_float")
    corp = float_corp(game, par=100)
    move_to_price(game, corp, 150)
    cy = game.players[2]
    cy.cash = 130
    legal = game.legal_stock_actions(cy, set())
    assert BuyShare("CEC", ShareSource.IPO) not in legal


def test_default_ipo_price_stays_par_after_float() -> None:
    game = new_game()
    corp = float_corp(game, par=100)
    move_to_price(game, corp, 150)
    assert game.ipo_price(corp) == 100


def test_serializer_reports_ipo_price() -> None:
    game = new_game(ipo_price_rule="market_after_float")
    corp = float_corp(game, par=100)
    move_to_price(game, corp, 150)
    state = session_to_json(GameSession(game, bots={}))
    cec = next(c for c in state["corporations"] if c["id"] == "CEC")
    assert cec["ipoPrice"] == 150 and cec["par"] == 100


# --- capitalization ------------------------------------------------------------------------


def test_incremental_capitalization_credits_par_per_ipo_share() -> None:
    game = new_game(capitalization="incremental")
    money = total_money(game)
    buy(game, 0, "CEC", par=80)
    corp = game.corp("CEC")
    assert corp.treasury == 160
    assert game.bank == 0
    buy(game, 1, "CEC")
    buy(game, 2, "CEC")
    buy(game, 1, "CEC")
    assert corp.floated
    assert corp.treasury == 5 * 80
    assert game.bank == 0
    buy(game, 2, "CEC")
    assert corp.treasury == 6 * 80
    assert total_money(game) == money


def test_incremental_capitalization_with_market_ipo_price_keeps_premium_in_bank() -> None:
    game = new_game(capitalization="incremental", ipo_price_rule="market_after_float")
    money = total_money(game)
    corp = float_corp(game, par=100)
    move_to_price(game, corp, 150)
    bank, treasury = game.bank, corp.treasury
    buy(game, 2, "CEC")
    assert corp.treasury == treasury + 100
    assert game.bank == bank + 50
    assert total_money(game) == money


def test_full_capitalization_pays_float_capital_shares_times_par_at_float() -> None:
    game = new_game(float_capital_shares=7)
    money = total_money(game)
    corp = float_corp(game, par=80)
    assert corp.treasury == 7 * 80
    assert total_money(game) == money


# --- homeworld_basic_income ------------------------------------------------------------


def test_income_floor_applies_to_a_corporation_without_pairs() -> None:
    game = new_game(homeworld_basic_income=30)
    corp = float_corp(game)
    assert game.revenue(corp).pairs == ()
    assert game.revenue(corp).total == 30
    treasury = corp.treasury
    game.settle_revenue(corp, pay=False)
    assert corp.last_revenue == 30
    assert corp.treasury == treasury + 30


def test_income_floor_does_not_reduce_higher_revenue() -> None:
    result = RevenueResult((), floor=30)
    assert result.total == 30 and result.pair_total == 0
    game = new_game(homeworld_basic_income=30)
    corp = float_corp(game)
    base = Game.new(["Ann", "Bo", "Cy"]).revenue(corp).total
    assert game.revenue(corp).total == max(base, 30)


def test_no_income_floor_by_default() -> None:
    game = new_game()
    corp = float_corp(game)
    assert game.revenue(corp).total == 0


# --- defaults ------------------------------------------------------------------------------


def test_variant_without_overrides_is_the_default_config() -> None:
    assert variant(DEFAULT_CONFIG) == DEFAULT_CONFIG == GameConfig()


def test_sweep_coerces_experimental_field_types() -> None:
    config = variant(DEFAULT_CONFIG, payout_step_fractions=[1, 2], zero_revenue_moves_price=False)
    assert config.payout_step_fractions == (1.0, 2.0)
    assert config.zero_revenue_moves_price is False
    with pytest.raises(ValueError):
        variant(DEFAULT_CONFIG, zero_revenue_moves_price=0)


def test_default_rules_reproduce_the_reference_game() -> None:
    """Worths captured when the 2-D market and tighter capital were adopted on 2026-09-28
    (3 greedy players, seed 1). A change here means the default rules or bot changed."""
    game, _ = play_one(1, 3, "greedy", DEFAULT_CONFIG)
    assert {p.id: game.player_worth(p) for p in game.players} == {
        "P1": 3473,
        "P2": 3500,
        "P3": 3318,
    }
    assert len(game.log) == 165
