"""The session driver, on the rules before the Death Star (``CLASSIC_CONFIG``)."""

import random

from bby18.actions import BuyShare, NoNetworkAction, PassStock, ShareSource
from bby18.game import BuyBlock
from bby18.bots import GreedyBot
from bby18.config import CLASSIC_CONFIG
from bby18.game import Game
from bby18.session import Dividend, GameSession, Phase
from bby18.state import CorpStatus


def start_lowest_par(session):
    starts = [a for a in session.legal_actions() if isinstance(a, BuyShare) and a.par == 60]
    session.apply(starts[0])


def test_session_walks_stock_then_operating_rounds():
    game = Game.new(["Ann", "Bo", "Cy"], CLASSIC_CONFIG)
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
    session = GameSession(Game.new(["Ann", "Bo"], CLASSIC_CONFIG))
    try:
        session.apply(Dividend.PAY)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_bots_play_until_a_human_is_needed_and_to_the_end():
    game = Game.new(["Human", "Bot1", "Bot2"], CLASSIC_CONFIG)
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


def test_undo_restores_state_before_the_last_submitted_action():
    game = Game.new(["Ann", "Bo"], CLASSIC_CONFIG)
    session = GameSession(game, record_undo=True)
    assert not session.can_undo
    start_lowest_par(session)
    assert session.game.corp("CEC").status is CorpStatus.PARRED
    session.undo()
    assert session.game.corp("CEC").status is CorpStatus.UNSTARTED
    assert session.current_player.id == "P1"
    assert not session.can_undo


def test_undo_takes_back_bot_moves_that_followed():
    game = Game.new(["Human", "Bot"], CLASSIC_CONFIG)
    session = GameSession(game, {"P2": GreedyBot(random.Random(1))}, record_undo=True)
    session.run_bots()
    log_before = len(session.game.log)
    start_lowest_par(session)
    assert len(session.game.log) > log_before + 1  # the bot answered
    session.undo()
    assert len(session.game.log) == log_before
    assert session.current_player.id == "P1"


def test_undo_with_nothing_recorded_raises():
    session = GameSession(Game.new(["Ann", "Bo"], CLASSIC_CONFIG))
    try:
        session.undo()
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_auto_forced_plays_single_legal_moves():
    game = Game.new(["Ann", "Bo", "Cy"], CLASSIC_CONFIG)
    session = GameSession(game, auto_forced=True)
    start_lowest_par(session)
    for _ in range(3):
        buys = [
            a
            for a in session.legal_actions()
            if isinstance(a, BuyShare) and a.corp_id == "CEC" and not a.par
        ]
        session.apply(buys[0])
    for _ in range(3):
        session.apply(PassStock())
    session.apply(NoNetworkAction())
    # With no revenue the only dividend choice is to withhold, so it was played for us.
    assert session.phase is Phase.NETWORK
    assert game.round_label == "OR1.2"
    assert game.log[session.automatic_log_start].text.startswith("withholds")


def test_operating_queue_stays_fixed_when_prices_change_mid_round():
    game = Game.new(["Bot1", "Bot2", "Bot3"], CLASSIC_CONFIG)
    bots = {p.id: GreedyBot(random.Random(i)) for i, p in enumerate(game.players)}
    session = GameSession(game, bots)
    # Step the bots one move at a time until an operating round has two corporations queued.
    while not (session.phase is Phase.NETWORK and len(session.operating_queue) >= 2):
        assert session.phase is not Phase.GAME_OVER, "no operating round with two corporations"
        session._apply_one(session._bot_choice())
    queue = session.operating_queue
    first = game.corp(queue[0])
    # Drop the first corporation to the bottom of the market, as a withhold streak would.
    first.market_cell = game.market.down(game.market.left(first.market_cell, 20), 20)
    assert [c.id for c in game.operating_order()] != queue
    assert session.operating_queue == queue


def test_buy_blocks_name_exactly_the_corporations_with_no_legal_buy():
    rng = random.Random(3)
    session = GameSession(Game.new(["Ann", "Bo", "Cy"]))
    stock_turns = 0
    while session.phase is not Phase.GAME_OVER:
        legal = session.legal_actions()
        if session.phase is Phase.STOCK:
            stock_turns += 1
            buyable = {a.corp_id for a in legal if isinstance(a, BuyShare)}
            blocked = set(session.buy_blocks())
            assert buyable | blocked == set(session.game.corporations)
            assert not buyable & blocked
        session.apply(rng.choice(legal))
    assert stock_turns > 50
    assert session.buy_blocks() == {}


def test_buy_blocks_name_the_current_players_holding_limit():
    session = GameSession(Game.new(["Ann", "Bo"], CLASSIC_CONFIG))
    ann = session.game.players[0]
    start_lowest_par(session)
    while ann.shares_in("CEC") < CLASSIC_CONFIG.max_holding_shares:
        if session.current_player is ann:
            session.apply(BuyShare("CEC", ShareSource.IPO))
        else:
            session.apply(PassStock())
    session.apply(PassStock())  # Bo, so it is Ann's turn again
    assert session.current_player is ann
    assert session.game.corp("CEC").ipo_shares > 0
    assert session.buy_blocks() == {"CEC": BuyBlock.HOLDING_LIMIT}
