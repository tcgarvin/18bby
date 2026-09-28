import random

from bby18.actions import BuyShare, NoNetworkAction, PassStock
from bby18.bots import GreedyBot
from bby18.game import Game
from bby18.session import Dividend, GameSession, Phase


def start_lowest_par(session):
    starts = [a for a in session.legal_actions() if isinstance(a, BuyShare) and a.par == 60]
    session.apply(starts[0])


def test_session_walks_stock_then_operating_rounds():
    game = Game.new(["Ann", "Bo", "Cy"])
    session = GameSession(game)
    assert session.phase is Phase.STOCK
    assert session.current_player.id == "P1"
    start_lowest_par(session)
    assert session.current_player.id == "P2"
    # Everyone piles into CEC until it floats.
    for _ in range(3):
        buys = [
            a
            for a in session.legal_actions()
            if isinstance(a, BuyShare) and a.corp_id == "CEC" and not a.par
        ]
        session.apply(buys[0])
    assert game.corp("CEC").floated
    for _ in range(3):
        session.apply(PassStock())
    assert session.phase is Phase.NETWORK
    assert session.current_corporation.id == "CEC"
    assert session.current_player.id == "P1"
    session.apply(NoNetworkAction())
    assert session.phase is Phase.DIVIDEND
    assert session.legal_actions() == [Dividend.WITHHOLD]  # no revenue yet
    session.apply(Dividend.WITHHOLD)
    # Second OR of the set, still only CEC operating.
    assert game.round_label == "OR1.2"
    session.apply(NoNetworkAction())
    session.apply(Dividend.WITHHOLD)
    assert session.phase is Phase.STOCK
    assert game.round_label == "SR2"


def test_illegal_action_is_rejected():
    session = GameSession(Game.new(["Ann", "Bo"]))
    try:
        session.apply(Dividend.PAY)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_bots_play_until_a_human_is_needed_and_to_the_end():
    game = Game.new(["Human", "Bot1", "Bot2"])
    bots = {"P2": GreedyBot(random.Random(1)), "P3": GreedyBot(random.Random(2))}
    session = GameSession(game, bots)
    session.run_bots()
    assert session.waiting_on_human()
    steps = 0
    while session.phase is not Phase.GAME_OVER:
        assert session.current_player.id == "P1"
        legal = session.legal_actions()
        session.apply(legal[0])
        steps += 1
        assert steps < 500
    assert game.is_over()
    total = (
        sum(p.cash for p in game.players)
        + sum(c.treasury for c in game.corporations.values())
        + game.bank
    )
    assert total == 1200
