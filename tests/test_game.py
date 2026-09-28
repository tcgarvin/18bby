import random

import pytest

from bby18.actions import BuyShare, Chart, NoNetworkAction, PassStock, SellShares, ShareSource
from bby18.bots import GreedyBot, RandomBot
from bby18.game import Game
from bby18.hexgrid import Direction as D
from bby18.hexgrid import Hex
from bby18.network import IllegalAction
from bby18.runner import run_game
from bby18.session import GameSession
from bby18.state import CorpStatus


@pytest.fixture
def game():
    return Game.new(["Ann", "Bo", "Cy"])


def buy(game, player, corp_id, source=ShareSource.IPO, par=0, sold=None):
    game.apply_stock_action(
        player, BuyShare(corp_id, source, par), sold if sold is not None else set()
    )


def float_corp(game, corp_id, par=60):
    p1, p2, p3 = game.players
    buy(game, p1, corp_id, par=par)  # president 2 shares
    buy(game, p2, corp_id)
    buy(game, p3, corp_id)
    assert game.corp(corp_id).status is CorpStatus.PARRED
    buy(game, p2, corp_id)
    return game.corp(corp_id)


def test_starting_cash_scales_with_player_count():
    assert Game.new(["a", "b"]).players[0].cash == 600
    assert Game.new(["a", "b", "c"]).players[0].cash == 400
    with pytest.raises(ValueError):
        Game.new(["a"])


def test_start_corp_sets_par_president_and_charges_double(game):
    ann = game.players[0]
    buy(game, ann, "CEC", par=70)
    cec = game.corp("CEC")
    assert cec.president == ann.id
    assert cec.par == 70 and game.price(cec) == 70
    assert ann.cash == 400 - 140
    assert ann.shares_in("CEC") == 2
    assert game.certificate_count(ann) == 1


def test_floats_at_half_sold_with_full_capitalization(game):
    cec = float_corp(game, "CEC", par=60)
    assert cec.floated
    assert cec.treasury == 480  # eight times par
    assert cec.ipo_shares == 5


def test_holding_and_certificate_limits(game):
    ann = game.players[0]
    buy(game, ann, "CEC", par=60)
    for _ in range(4):
        buy(game, ann, "CEC")
    assert ann.shares_in("CEC") == 6
    with pytest.raises(IllegalAction):
        buy(game, ann, "CEC")


def test_no_sales_in_first_stock_round_then_sales_drop_price(game):
    cec = float_corp(game, "CEC")
    bo = game.players[1]
    assert not any(isinstance(a, SellShares) for a in game.legal_stock_actions(bo, set()))
    game.stock_rounds_played = 1
    sold = set()
    game.apply_stock_action(bo, SellShares("CEC", 2), sold)
    assert game.price(cec) == 40
    assert cec.pool_shares == 2
    assert bo.cash == 400 - 120 + 120
    with pytest.raises(IllegalAction):
        buy(game, bo, "CEC", sold=sold)  # cannot rebuy what you sold this round
    assert "CEC" in sold


def test_president_cannot_dump_unless_someone_can_take_over(game):
    cec = float_corp(game, "CEC")
    ann, bo, _ = game.players
    game.stock_rounds_played = 1
    assert bo.shares_in("CEC") == 2
    game.apply_stock_action(ann, SellShares("CEC", 1), set())
    assert cec.president == bo.id
    # Bo now presides with 2; Ann has 1. Bo cannot sell out (Ann has only 1).
    assert not game._can_sell(bo, cec, 1)


def test_operating_turn_charts_and_pays_dividends(game):
    cec = float_corp(game, "CEC")
    legal = game.legal_network_actions(cec)
    charts = [a for a in legal if isinstance(a, Chart)]
    assert charts and NoNetworkAction() in legal
    # Corellia (-5,3) -> (-4,2) NE exit reaches Kuat? No: Kuat is (-3,2), two steps. Chart toward Alderaan (-4,1)
    action = Chart(Hex(-4, 2), frozenset({D.SW, D.NW}), 50)
    assert action in charts
    game.apply_network_action(cec, action)
    assert cec.treasury == 430
    result = game.revenue(cec)
    # Corellia (I/S) <-> Alderaan (M): Industry-Market typed pair.
    assert result.total == 30
    game.settle_revenue(cec, pay=True)
    ann, bo, cy = game.players
    assert ann.cash == 400 - 120 + 6  # 3/share x 2
    assert bo.cash == 400 - 120 + 6
    assert cy.cash == 400 - 60 + 3
    assert cec.treasury == 430  # unheld shares pay nobody
    assert game.price(cec) == 70


def test_withholding_drops_price_and_keeps_cash(game):
    cec = float_corp(game, "CEC", par=70)
    game.settle_revenue(cec, pay=False)
    assert game.price(cec) == 60
    assert cec.treasury == 560


def test_operating_order_by_price_then_float_order(game):
    cec = float_corp(game, "CEC", par=60)
    kdy = float_corp(game, "KDY", par=60)
    assert [c.id for c in game.operating_order()] == ["CEC", "KDY"]
    game.settle_revenue(cec, pay=False)
    assert [c.id for c in game.operating_order()] == ["KDY", "CEC"]


def test_stock_round_priority_moves_past_last_actor(game):
    class StartOnce:
        def __init__(self):
            self.done = False

        def choose_stock_action(self, g, player, legal):
            if not self.done:
                self.done = True
                start = [a for a in legal if isinstance(a, BuyShare) and a.par == 60]
                if start:
                    return start[0]
            return PassStock()

        def choose_network_action(self, g, corp, legal):
            return NoNetworkAction()

        def choose_pay_dividends(self, g, corp, revenue):
            return True

    deciders = {p.id: StartOnce() for p in game.players}
    session = GameSession(game)
    while session.phase.value == "stock":
        player = session.current_player
        session.apply(
            deciders[player.id].choose_stock_action(game, player, session.legal_actions())
        )
    # Everyone started a corporation once; the last actor was player 3, so priority is player 1.
    assert game.priority_player == 0
    assert sum(1 for c in game.corporations.values() if c.status is CorpStatus.PARRED) == 3


@pytest.mark.parametrize("bot_cls", [GreedyBot, RandomBot])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_full_bot_games_complete_and_conserve_money(bot_cls, seed):
    game = Game.new(["a", "b", "c"])
    deciders = {p.id: bot_cls(random.Random(seed + i)) for i, p in enumerate(game.players)}
    run_game(game, deciders)
    assert game.is_over()
    player_cash = sum(p.cash for p in game.players)
    corp_cash = sum(c.treasury for c in game.corporations.values())
    assert player_cash + corp_cash + game.bank == 3 * 400
