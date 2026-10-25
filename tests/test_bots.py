import random

import pytest

from bby18.actions import BuyShare, PassStock, SellShares, ShareSource, StockAction
from bby18.bots import GreedyBot, GreedyPolicy
from bby18.config import DEFAULT_CONFIG
from bby18.game import Game
from bby18.playtest import BOT_KINDS, make_deciders, play_one, seat_kinds
from bby18.runner import run_game
from bby18.state import Player
from bby18.sweep import GameTask, run_task, validate_tasks


def _play(seed: int, policy: GreedyPolicy | None) -> Game:
    """A 3-player greedy game seeded like ``play_one``; ``None`` omits the policy argument."""
    game = Game.new([f"Player {i + 1}" for i in range(3)], DEFAULT_CONFIG, seed)
    rng = random.Random(seed)
    deciders = {
        p.id: (
            GreedyBot(random.Random(rng.random()))
            if policy is None
            else GreedyBot(random.Random(rng.random()), policy)
        )
        for p in game.players
    }
    run_game(game, deciders)
    return game


def _log(game: Game) -> list[str]:
    return [str(e) for e in game.log]


def test_default_policy_matches_bot_without_policy():
    assert _log(_play(1, GreedyPolicy())) == _log(_play(1, None))


def test_greedy_kind_is_the_default_policy():
    game, _ = play_one(1, 3, "greedy", DEFAULT_CONFIG)
    assert _log(game) == _log(_play(1, None))


def test_default_policy_starts_corporations_in_seat_order():
    game = _play(1, GreedyPolicy())
    presidents = {c.id: c.president for c in game.corporations.values() if c.floated}
    assert presidents == {"CEC": "P1", "KDY": "P2", "CSC": "P3"}


def test_random_start_order_varies_across_seeds():
    policy = GreedyPolicy(start_order="random")
    assignments = set()
    for seed in range(1, 7):
        game = _play(seed, policy)
        assignments.add(frozenset((c.id, c.president) for c in game.corporations.values()))
    assert len(assignments) > 1


def test_random_start_order_lets_p1_start_different_corporations():
    policy = GreedyPolicy(start_order="random")
    p1_corps = set()
    for seed in range(1, 9):
        game = _play(seed, policy)
        p1_corps |= {c.id for c in game.corporations.values() if c.president == "P1"}
    assert len(p1_corps) >= 2


def test_two_presidencies_allowed():
    policy = GreedyPolicy(start_order="random", max_presidencies=2)
    most = 0
    for seed in range(1, 6):
        game = _play(seed, policy)
        for p in game.players:
            most = max(most, sum(1 for c in game.corporations.values() if c.president == p.id))
    assert most >= 2


def test_best_home_ranks_by_nearby_revenue():
    game = Game.new(["a", "b", "c"])
    bot = GreedyBot(random.Random(1), GreedyPolicy(start_order="best_home"))
    potentials = {cid: bot.home_potential(game, c) for cid, c in game.corporations.items()}
    assert all(v >= 0 for v in potentials.values())
    buys = [a for a in game.legal_stock_actions(game.players[0], set()) if isinstance(a, BuyShare)]
    choice = bot.choose_stock_action(game, game.players[0], list(buys))
    assert isinstance(choice, BuyShare)
    assert potentials[choice.corp_id] == max(potentials.values())


@pytest.mark.parametrize("par_choice", ["min", "max", "mid", "random"])
def test_par_choice_picks_an_affordable_par(par_choice):
    game = Game.new(["a", "b", "c"])
    player = game.players[0]
    bot = GreedyBot(random.Random(1), GreedyPolicy(par_choice=par_choice))
    legal = game.legal_stock_actions(player, set())
    choice = bot.choose_stock_action(game, player, legal)
    assert choice in legal
    assert isinstance(choice, BuyShare)
    pars = sorted(game.config.par_prices)
    floatable = [p for p in pars if p * game.config.float_threshold_shares <= player.cash]
    expected = {"min": pars[0], "max": floatable[-1], "mid": pars[len(pars) // 2]}
    if par_choice in expected:
        assert choice.par == expected[par_choice]


class _RecordingBot(GreedyBot):
    def __init__(self, rng: random.Random, policy: GreedyPolicy) -> None:
        super().__init__(rng, policy)
        self.sales: list[SellShares] = []

    def choose_stock_action(
        self, game: Game, player: Player, legal: list[StockAction]
    ) -> StockAction:
        action = super().choose_stock_action(game, player, legal)
        if isinstance(action, SellShares):
            self.sales.append(action)
        return action


def _losing_position(stock_rounds_played: int) -> tuple[Game, Player]:
    """P1 presides over CEC; P2 holds one CEC share and CEC trades below par."""
    game = Game.new(["a", "b", "c"])
    p1, p2 = game.players[0], game.players[1]
    game.apply_stock_action(p1, BuyShare("CEC", ShareSource.IPO, 100), set())
    game.apply_stock_action(p2, BuyShare("CEC", ShareSource.IPO), set())
    cec = game.corp("CEC")
    cec.market_cell = game.market.left(cec.market_cell, 2)
    game.stock_rounds_played = stock_rounds_played
    return game, p2


def test_sell_losers_sells_one_share_of_a_loser_when_legal():
    game, p2 = _losing_position(stock_rounds_played=1)
    legal = game.legal_stock_actions(p2, set())
    bot = GreedyBot(random.Random(1), GreedyPolicy(sell_losers=True))
    action = bot.choose_stock_action(game, p2, legal)
    assert action == SellShares("CEC", 1)
    assert action in legal


def test_sell_losers_does_not_sell_when_selling_is_illegal():
    game, p2 = _losing_position(stock_rounds_played=0)
    legal = game.legal_stock_actions(p2, set())
    assert not any(isinstance(a, SellShares) for a in legal)
    bot = GreedyBot(random.Random(1), GreedyPolicy(sell_losers=True))
    assert not isinstance(bot.choose_stock_action(game, p2, legal), SellShares)


def test_sell_losers_keeps_presidencies():
    game, _ = _losing_position(stock_rounds_played=1)
    p1 = game.players[0]
    legal = game.legal_stock_actions(p1, set())
    bot = GreedyBot(random.Random(1), GreedyPolicy(sell_losers=True))
    assert not isinstance(bot.choose_stock_action(game, p1, legal), SellShares)


def test_sell_losers_bot_plays_only_legal_actions_in_full_games():
    # The session rejects illegal actions, so completing games is the legality check.
    for seed in range(1, 4):
        game, _ = play_one(seed, 3, "greedy-sell", DEFAULT_CONFIG)
        assert game.is_over()


def test_default_policy_never_sells():
    game = Game.new(["a", "b", "c"])
    rng = random.Random(1)
    bots = {p.id: _RecordingBot(random.Random(rng.random()), GreedyPolicy()) for p in game.players}
    run_game(game, dict(bots))
    assert all(not b.sales for b in bots.values())


def test_hold_policy_withholds_low_revenue():
    game = Game.new(["a", "b", "c"])
    corp = next(iter(game.corporations.values()))
    corp.treasury = 1000
    bot = GreedyBot(random.Random(1), GreedyPolicy(withhold_when_revenue_below=60))
    assert not bot.choose_pay_dividends(game, corp, 50)
    assert bot.choose_pay_dividends(game, corp, 60)


def test_invalid_policy_rejected():
    with pytest.raises(ValueError):
        GreedyPolicy(start_order="alphabetical")
    with pytest.raises(ValueError):
        GreedyPolicy(par_choice="median")


def test_every_bot_kind_completes_a_game():
    for kind in BOT_KINDS:
        game, _ = play_one(2, 3, kind, DEFAULT_CONFIG)
        assert game.is_over()


def test_mix_string_assigns_kinds_round_robin():
    assert seat_kinds("mix:greedy,greedy-rs,greedy-best", 4) == [
        "greedy",
        "greedy-rs",
        "greedy-best",
        "greedy",
    ]
    assert seat_kinds("greedy-hold", 2) == ["greedy-hold", "greedy-hold"]
    game = Game.new(["a", "b", "c"])
    deciders = make_deciders(game, "mix:random,greedy-best", random.Random(1))
    assert type(deciders["P1"]).__name__ == "RandomBot"
    assert isinstance(deciders["P2"], GreedyBot)
    assert deciders["P2"].policy.start_order == "best_home"
    assert type(deciders["P3"]).__name__ == "RandomBot"


@pytest.mark.parametrize("bad", ["nope", "mix:", "mix:greedy,,random", "mix:greedy,nope"])
def test_bad_bot_strings_rejected(bad):
    with pytest.raises(ValueError):
        seat_kinds(bad, 3)
    with pytest.raises(ValueError):
        validate_tasks([GameTask("base", DEFAULT_CONFIG, 1, 3, bad)])


def test_mixed_sweep_row_records_bot_string():
    row = run_task(GameTask("base", DEFAULT_CONFIG, 1, 3, "mix:greedy,greedy-rs,greedy-best"))
    assert row["bot"] == "mix:greedy,greedy-rs,greedy-best"


def _parred_position(policy: GreedyPolicy) -> tuple[Game, Player, GreedyBot]:
    """P1 has started CEC, which has not floated; it is P1's turn again."""
    game = Game.new(["a", "b", "c"])
    p1 = game.players[0]
    game.apply_stock_action(p1, BuyShare("CEC", ShareSource.IPO, 100), set())
    assert not game.corp("CEC").floated
    return game, p1, GreedyBot(random.Random(1), policy)


def test_float_seeking_bot_buys_its_own_unfloated_corporation_before_starting_another():
    game, p1, bot = _parred_position(GreedyPolicy(max_presidencies=2, par_choice="max"))
    legal = game.legal_stock_actions(p1, set())
    assert bot.choose_stock_action(game, p1, legal) == BuyShare("CEC", ShareSource.IPO)


def test_float_seeking_bot_ignores_cash_reserve_for_its_own_float():
    game, p1, bot = _parred_position(GreedyPolicy(max_presidencies=2))
    p1.cash = 100
    legal = game.legal_stock_actions(p1, set())
    assert bot.choose_stock_action(game, p1, legal) == BuyShare("CEC", ShareSource.IPO)


def test_default_bot_does_not_seek_float():
    game, p1, bot = _parred_position(GreedyPolicy())
    p1.cash = 100
    legal = game.legal_stock_actions(p1, set())
    assert bot.choose_stock_action(game, p1, legal) == PassStock()


@pytest.mark.parametrize("kind", ["greedy-rs", "greedy-max", "greedy-best"])
def test_multi_presidency_kinds_float_corporations(kind):
    floated = [play_one(seed, 3, kind, DEFAULT_CONFIG)[1].floated for seed in range(1, 4)]
    assert min(floated) >= 2


def test_max_par_falls_back_to_highest_affordable_when_none_floats_alone():
    game = Game.new(["a", "b", "c"])
    player = game.players[0]
    player.cash = 250  # affords a 2-share president's certificate up to 100, floats alone at none
    bot = GreedyBot(random.Random(1), GreedyPolicy(par_choice="max"))
    choice = bot.choose_stock_action(game, player, game.legal_stock_actions(player, set()))
    assert isinstance(choice, BuyShare) and choice.par == 100
