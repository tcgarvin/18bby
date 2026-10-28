import random
from dataclasses import replace

import pytest

from bby18.actions import BuyShare, PassStock, SellShares, ShareSource, StockAction
from bby18.bots import GreedyBot, GreedyPolicy
from bby18.config import CLASSIC_CONFIG, DEFAULT_CONFIG, CorporationSpec
from bby18.game import Game
from bby18.playtest import BOT_KINDS, make_deciders, play_one, seat_kinds
from bby18.runner import run_game
from bby18.state import NO_PLAYER, CorpStatus, Player
from bby18.sweep import GameTask, run_task, validate_tasks


def _play(seed: int, policy: GreedyPolicy | None) -> Game:
    """A 3-player greedy game seeded like ``play_one``; ``None`` omits the policy argument."""
    game = Game.new([f"Player {i + 1}" for i in range(3)], CLASSIC_CONFIG, seed)
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
    game, _ = play_one(1, 3, "greedy", CLASSIC_CONFIG)
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
    game = Game.new(["a", "b", "c"], CLASSIC_CONFIG)
    bot = GreedyBot(random.Random(1), GreedyPolicy(start_order="best_home"))
    potentials = {cid: bot.home_potential(game, c) for cid, c in game.corporations.items()}
    assert all(v >= 0 for v in potentials.values())
    buys = [a for a in game.legal_stock_actions(game.players[0], set()) if isinstance(a, BuyShare)]
    choice = bot.choose_stock_action(game, game.players[0], list(buys))
    assert isinstance(choice, BuyShare)
    assert potentials[choice.corp_id] == max(potentials.values())


@pytest.mark.parametrize("par_choice", ["min", "max", "mid", "random"])
def test_par_choice_picks_an_affordable_par(par_choice):
    game = Game.new(["a", "b", "c"], CLASSIC_CONFIG)
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
    game = Game.new(["a", "b", "c"], CLASSIC_CONFIG)
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
        game, _ = play_one(seed, 3, "greedy-sell", CLASSIC_CONFIG)
        assert game.is_over()


def test_default_policy_never_sells():
    game = Game.new(["a", "b", "c"], CLASSIC_CONFIG)
    rng = random.Random(1)
    bots = {p.id: _RecordingBot(random.Random(rng.random()), GreedyPolicy()) for p in game.players}
    run_game(game, dict(bots))
    assert all(not b.sales for b in bots.values())


def test_hold_policy_withholds_low_revenue():
    game = Game.new(["a", "b", "c"], CLASSIC_CONFIG)
    corp = next(iter(game.corporations.values()))
    corp.treasury = 1000
    bot = GreedyBot(random.Random(1), GreedyPolicy(withhold_when_revenue_below=60))
    assert not bot.choose_pay_dividends(game, corp, 50)
    assert bot.choose_pay_dividends(game, corp, 60)


def _started_cec() -> tuple[Game, Player]:
    game = Game.new(["a", "b", "c"], CLASSIC_CONFIG)
    p1 = game.players[0]
    game.apply_stock_action(p1, BuyShare("CEC", ShareSource.IPO, 100), set())
    return game, p1


def test_targeted_withholding_withholds_only_for_an_unaffordable_gaining_build():
    game, _ = _started_cec()
    corp = game.corp("CEC")
    bot = GreedyBot(random.Random(1), GreedyPolicy(withhold_for_builds=True))
    corp.treasury = 0
    assert not bot.choose_pay_dividends(game, corp, 30)
    corp.treasury = 10**6
    assert bot.choose_pay_dividends(game, corp, 30)


def test_withhold_until_round_withholds_early_then_pays():
    game, _ = _started_cec()
    corp = game.corp("CEC")
    corp.treasury = 1000
    bot = GreedyBot(random.Random(1), GreedyPolicy(withhold_until_round=2, pay_threshold=0))
    game.round_number = 1
    assert not bot.choose_pay_dividends(game, corp, 50)
    game.round_number = 2
    assert bot.choose_pay_dividends(game, corp, 50)


def test_pay_when_steps_pays_a_big_payout_despite_withholding_early():
    game, _ = _started_cec()
    corp = game.corp("CEC")
    policy = GreedyPolicy(withhold_until_round=3, pay_when_steps=2)
    bot = GreedyBot(random.Random(1), policy)
    price = game.price(corp)
    assert bot.choose_pay_dividends(game, corp, 2 * price)
    assert not bot.choose_pay_dividends(game, corp, price)


def test_last_start_round_stops_starting_corporations():
    game = Game.new(["a", "b", "c"], CLASSIC_CONFIG)
    player = game.players[0]
    game.round_number = 3
    bot = GreedyBot(random.Random(1), GreedyPolicy(last_start_round=2))
    action = bot.choose_stock_action(game, player, game.legal_stock_actions(player, set()))
    assert action == PassStock()


def test_dump_rivals_sells_the_richer_leaders_corporation():
    game, p2 = _losing_position(stock_rounds_played=1)
    game.players[0].cash += 1000
    bot = GreedyBot(random.Random(1), GreedyPolicy(dump_rivals=True))
    assert bot.choose_stock_action(game, p2, game.legal_stock_actions(p2, set())) == SellShares(
        "CEC", 1
    )


def test_dump_rivals_leaves_a_poorer_president_alone():
    game, p2 = _losing_position(stock_rounds_played=1)
    p2.cash += 1000
    bot = GreedyBot(random.Random(1), GreedyPolicy(dump_rivals=True))
    action = bot.choose_stock_action(game, p2, game.legal_stock_actions(p2, set()))
    assert not isinstance(action, SellShares)


def test_invalid_policy_rejected():
    with pytest.raises(ValueError):
        GreedyPolicy(start_order="alphabetical")
    with pytest.raises(ValueError):
        GreedyPolicy(par_choice="median")


def test_every_bot_kind_completes_a_game():
    for kind in BOT_KINDS:
        game, _ = play_one(2, 3, kind, CLASSIC_CONFIG)
        assert game.is_over()


def test_mix_string_assigns_kinds_round_robin():
    assert seat_kinds("mix:greedy,greedy-rs,greedy-best", 4) == [
        "greedy",
        "greedy-rs",
        "greedy-best",
        "greedy",
    ]
    assert seat_kinds("greedy-hold", 2) == ["greedy-hold", "greedy-hold"]
    game = Game.new(["a", "b", "c"], CLASSIC_CONFIG)
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
        validate_tasks([GameTask("base", CLASSIC_CONFIG, 1, 3, bad)])


def test_mixed_sweep_row_records_bot_string():
    row = run_task(GameTask("base", CLASSIC_CONFIG, 1, 3, "mix:greedy,greedy-rs,greedy-best"))
    assert row["bot"] == "mix:greedy,greedy-rs,greedy-best"


def _parred_position(policy: GreedyPolicy) -> tuple[Game, Player, GreedyBot]:
    """P1 has started CEC, which has not floated; it is P1's turn again."""
    game = Game.new(["a", "b", "c"], CLASSIC_CONFIG)
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
    floated = [play_one(seed, 3, kind, CLASSIC_CONFIG)[1].floated for seed in range(1, 4)]
    assert min(floated) >= 2


def test_max_par_falls_back_to_highest_affordable_when_none_floats_alone():
    game = Game.new(["a", "b", "c"], CLASSIC_CONFIG)
    player = game.players[0]
    player.cash = 250  # affords a 2-share president's certificate up to 100, floats alone at none
    bot = GreedyBot(random.Random(1), GreedyPolicy(par_choice="max"))
    choice = bot.choose_stock_action(game, player, game.legal_stock_actions(player, set()))
    assert isinstance(choice, BuyShare) and choice.par == 100


def test_noise_free_policy_plays_identically_with_an_explicit_zero():
    assert _log(_play(3, GreedyPolicy(noise=0.0))) == _log(_play(3, None))


def test_noisy_bot_plays_differently_and_legally():
    game = _play(3, GreedyPolicy(noise=0.5))
    assert game.is_over()
    assert _log(game) != _log(_play(3, None))


def test_fully_careless_bot_still_starts_a_corporation():
    game = Game.new(["a", "b", "c"], CLASSIC_CONFIG)
    player = game.players[0]
    bot = GreedyBot(random.Random(1), GreedyPolicy(noise=1.0))
    for _ in range(20):
        choice = bot.choose_stock_action(game, player, game.legal_stock_actions(player, set()))
        assert isinstance(choice, BuyShare)
        assert game.corp(choice.corp_id).status is CorpStatus.UNSTARTED


def test_fully_careless_bot_still_buys_toward_floating_its_own_corporation():
    game = Game.new(["a", "b", "c"], CLASSIC_CONFIG)
    player = game.players[0]
    bot = GreedyBot(random.Random(1), GreedyPolicy(par_choice="max", noise=1.0))
    start = bot.choose_stock_action(game, player, game.legal_stock_actions(player, set()))
    assert isinstance(start, BuyShare)
    game.apply_stock_action(player, start, set())
    assert game.corp(start.corp_id).status is CorpStatus.PARRED
    for _ in range(20):
        choice = bot.choose_stock_action(game, player, game.legal_stock_actions(player, set()))
        assert choice == BuyShare(start.corp_id, ShareSource.IPO)


def test_diversifier_floats_what_it_starts():
    for seed in range(1, 6):
        game, _ = play_one(seed, 3, "diversifier", CLASSIC_CONFIG)
        started = [c for c in game.corporations.values() if c.president != NO_PLAYER]
        assert started and all(c.floated for c in started)


def test_noise_out_of_range_rejected():
    with pytest.raises(ValueError):
        GreedyPolicy(noise=1.5)


def test_noisy_kind_string_builds_a_noisy_stable_bot():
    game, _ = play_one(2, 3, "mix:baron~0.4,builder", CLASSIC_CONFIG)
    assert game.is_over()
    with pytest.raises(ValueError):
        seat_kinds("baron~lots", 3)


def test_start_order_kind_string_sets_the_start_order():
    deciders = make_deciders(
        Game.new(["A", "B", "C"], CLASSIC_CONFIG, 1), "baron@site~0.2", random.Random(1)
    )
    for bot in deciders.values():
        assert isinstance(bot, GreedyBot)
        assert bot.policy.start_order == "site"
        assert bot.policy.noise == 0.2
    with pytest.raises(ValueError):
        seat_kinds("baron@nearest", 3)


def test_site_appeal_is_the_contract_value_near_the_site_and_nothing_far_away():
    game = Game.new(["A", "B", "C"], DEFAULT_CONFIG, 1)
    site = game.death_star_site()
    assert site is not None
    bot = GreedyBot(random.Random(1), GreedyPolicy(start_order="site", contract_weight=2.0))
    radius = bot.policy.home_radius
    for corp in game.corporations.values():
        distance = game.homeworld(corp).distance(site)
        appeal = bot.site_appeal(game, corp)
        if distance <= radius:
            assert appeal == 2.0 * game.contract_value()
        elif distance >= 2 * radius:
            assert appeal == 0
        else:
            assert 0 < appeal < 2.0 * game.contract_value()


def test_site_start_order_without_a_site_plays_like_best_home():
    best_home = _play(4, GreedyPolicy(start_order="best_home"))
    site = _play(4, GreedyPolicy(start_order="site"))
    assert _log(site) == _log(best_home)


def test_site_start_order_prefers_the_corporation_nearest_the_site():
    game = Game.new(["A", "B", "C"], DEFAULT_CONFIG, 1)
    bot = GreedyBot(random.Random(1), GreedyPolicy(start_order="site", contract_weight=10.0))
    player = game.players[0]
    legal = game.legal_stock_actions(player, set())
    starts = bot._start_options(game, player, [a for a in legal if isinstance(a, BuyShare)])
    site = game.death_star_site()
    assert site is not None
    nearest = min(game.homeworld(c).distance(site) for c in game.corporations.values())
    assert game.homeworld(game.corp(starts[0].corp_id)).distance(site) == nearest


def test_six_corporation_game_with_site_aware_bots_completes():
    config = replace(
        DEFAULT_CONFIG,
        corporations=DEFAULT_CONFIG.corporations
        + (
            CorporationSpec("IGB", "InterGalactic Banking Clan", "Mygeeto"),
            CorporationSpec("RRC", "Ryloth Ryll Combine", "Ryloth"),
        ),
    )
    game, _ = play_one(5, 3, "mix:baron@site,contractor@site,staller@site", config)
    assert game.is_over()
    assert len(game.corporations) == 6
