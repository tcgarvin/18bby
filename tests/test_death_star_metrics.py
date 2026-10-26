"""Sweep measurements of the experimental Death Star rules, and their report."""

import argparse
import json
import re
from collections import Counter
from dataclasses import replace

import pytest

from bby18.actions import BuyFleet, BuyShare, NoNetworkAction, PassStock, SellShares, ShareSource
from bby18.cli import death_star_command
from bby18.config import DEFAULT_CONFIG
from bby18.death_star_metrics import (
    ROW_PREFIX,
    DeathStarRecorder,
    round_point,
    stock_round_before,
)
from bby18.death_star_report import death_star_report, variant_report
from bby18.game import Game
from bby18.playtest import play_one
from bby18.session import Dividend, GameSession, Phase, PlayedMove

RULES = replace(DEFAULT_CONFIG, death_star_rules=True)


# --- the clock --------------------------------------------------------------------------------


def test_round_labels_map_to_one_clock_with_stock_rounds_at_halves():
    assert round_point("SR1", 2).clock == 0.5
    assert round_point("OR1.1", 2).clock == 1
    assert round_point("OR1.2", 2).clock == 2
    assert round_point("SR2", 2).clock == 2.5
    point = round_point("OR8.2", 2)
    assert (point.round, point.operating, point.clock) == (8, 2, 16)
    assert round_point("SR3", 2).is_stock and not point.is_stock
    assert round_point("OR2.3", 3).clock == 6


@pytest.mark.parametrize("label", ["setup", "end", "OR1", "SR"])
def test_labels_outside_a_round_have_no_clock(label):
    with pytest.raises(ValueError):
        round_point(label, 2)


def test_stock_round_before_a_moment_is_the_latest_at_or_before_it():
    assert stock_round_before(4.5, 2) == 4.5
    assert stock_round_before(5, 2) == 4.5
    assert stock_round_before(6, 2) == 4.5
    assert stock_round_before(4, 2) == 2.5
    assert stock_round_before(1, 2) == 0.5


# --- the recorder on scripted moves -----------------------------------------------------------


class Script:
    """Feeds hand-made moves to a recorder, changing the game state the way the session would."""

    def __init__(self, fleets: int = 1) -> None:
        self.game = Game.new(["Ann", "Bo", "Cy"], RULES, seed=1)
        p1, p2, p3 = self.game.players
        for player, par in ((p1, 60), (p2, 0), (p3, 0), (p2, 0)):
            self.game.apply_stock_action(player, BuyShare("CEC", ShareSource.IPO, par), set())
        self.cec = self.game.corp("CEC")
        self.cec.fleets = fleets
        self.session = GameSession(self.game)
        self.recorder = DeathStarRecorder(self.game)

    def move(self, phase, label, action, *, after="", corp="CEC", actor="P1", revenue=0):
        """Record one move made in round ``label``; ``after`` is the round label once it is
        played (the same round unless the move ends it)."""
        self.game.round_label = after or label
        operating = phase is not Phase.STOCK
        played = PlayedMove(
            action, True, phase, label, actor, corp if operating else "", 0, revenue
        )
        self.recorder(self.session, played)

    def metrics(self):
        return self.recorder.metrics(self.game)


def test_recorder_needs_the_rules_on():
    with pytest.raises(ValueError):
        DeathStarRecorder(Game.new(["Ann", "Bo"], DEFAULT_CONFIG))


def test_contract_cubes_score_the_value_of_the_stage_being_built_before_the_move():
    script = Script()
    track = script.game.death_star
    track.cubes = 2
    script.move(Phase.DIVIDEND, "OR1.1", Dividend.PAY, revenue=100)
    track.cubes = 7  # fills stage 1 (6 cubes), worth 40 until it resolves
    script.game.resolve_death_star()
    script.game.round_number = 1
    script.move(Phase.DIVIDEND, "OR1.2", Dividend.WITHHOLD, after="SR2", revenue=90)
    track.cubes = 8
    script.move(Phase.STOCK, "SR2", PassStock())
    cec = script.metrics().corps["CEC"]
    assert (cec.contract_pairs, cec.contract_revenue, cec.revenue_total) == (7, 280, 190)
    metrics = script.metrics()
    assert (metrics.contract_cubes, metrics.empire_cubes) == (7, 1)
    assert metrics.stage_filled_at == (2.0, 0.0, 0.0, 0.0)
    assert metrics.stage_resolved_at == (2.0, 0.0, 0.0, 0.0)
    assert cec.fleets_seized == 1 and cec.final_fleets == 0
    assert metrics.fleets_end_round == {1: 0}


def test_fleet_purchases_and_seizures_are_counted_per_corporation():
    script = Script(fleets=0)
    for cost in (60, 60):
        script.cec.fleets += 1
        script.game.fleets_sold += 1
        script.move(Phase.FLEET, "OR1.1", BuyFleet(cost))
    script.game.death_star.cubes = 6
    script.game.resolve_death_star()
    script.move(Phase.DIVIDEND, "OR1.1", Dividend.PAY, after="OR1.2", revenue=50)
    metrics = script.metrics()
    cec = metrics.corps["CEC"]
    assert (cec.fleets_bought, cec.fleet_spend, cec.fleets_seized, cec.final_fleets) == (
        2,
        120,
        1,
        1,
    )
    assert (metrics.fleets_sold, metrics.final_fleet_tier) == (2, 1)


def test_withholds_near_a_seizure_are_the_two_operating_rounds_up_to_its_filling():
    script = Script(fleets=4)
    choices = [
        ("OR1.1", Dividend.PAY, 50),
        ("OR1.2", Dividend.PAY, 50),
        ("OR2.1", Dividend.WITHHOLD, 50),
        ("OR2.2", Dividend.WITHHOLD, 0),  # forced: not a choice
        ("OR2.2", Dividend.WITHHOLD, 60),
        ("OR3.1", Dividend.PAY, 60),
    ]
    for label, choice, revenue in choices:
        if label == "OR2.2" and revenue:
            script.game.death_star.cubes = 6  # the seizure stage fills in OR2.2 (clock 4)
        script.move(Phase.DIVIDEND, label, choice, revenue=revenue)
    metrics = script.metrics()
    assert metrics.stage_filled_at[0] == 4
    assert (metrics.dividend_choices, metrics.withholds) == (5, 2)
    assert (metrics.dividend_choices_near_seizure, metrics.withholds_near_seizure) == (2, 2)


def test_sales_in_the_stock_round_before_a_seizure_or_site_move_are_counted_apart():
    script = Script(fleets=4)
    script.move(Phase.STOCK, "SR1", PassStock())  # no sales allowed: not a sale round
    script.move(Phase.STOCK, "SR2", SellShares("CEC", 2))
    script.move(Phase.STOCK, "SR2", SellShares("CEC", 1))
    script.move(Phase.STOCK, "SR3", SellShares("CEC", 1))
    script.game.death_star.cubes = 6
    script.move(Phase.DIVIDEND, "OR3.1", Dividend.PAY, revenue=50)  # clock 5, after SR3
    script.move(Phase.STOCK, "SR4", PassStock())
    metrics = script.metrics()
    assert (metrics.sale_rounds, metrics.shares_sold) == (3, 4)
    assert (metrics.sale_rounds_before_stage, metrics.shares_sold_before_stage) == (1, 1)


def test_bankruptcy_records_the_round_and_the_president_at_closing():
    script = Script(fleets=0)
    script.cec.treasury = 0
    script.game.close_bankrupt(script.cec)
    script.move(Phase.NETWORK, "OR4.2", NoNetworkAction(), actor="P2")
    metrics = script.metrics()
    cec = metrics.corps["CEC"]
    assert (cec.closed, cec.closed_at, cec.closed_round, cec.closed_president) == (
        True,
        8.0,
        4,
        "P2",
    )
    assert metrics.bankruptcies == 1
    assert not metrics.corps["KDY"].closed and metrics.corps["KDY"].closed_president == ""


def test_price_change_across_the_site_move_is_measured_between_operating_round_ends():
    script = Script(fleets=2)
    game = script.game
    game.death_star.cubes = 12  # a seizure, then the site move, at the end of OR2.2
    game.resolve_death_star()
    script.move(Phase.DIVIDEND, "OR2.2", Dividend.PAY, after="SR3", revenue=50)
    before = game.price(script.cec)
    script.cec.market_cell = game.market.left(game.market.left(script.cec.market_cell))
    script.move(Phase.DIVIDEND, "OR3.1", Dividend.WITHHOLD, after="OR3.2", revenue=50)
    change = game.price(script.cec) - before
    metrics = script.metrics()
    assert change < 0
    assert (metrics.site_move_price_delta, metrics.site_move_price_corps) == (change, 1)
    assert (metrics.or_price_delta, metrics.or_price_corps) == (change, 1)
    assert metrics.stage_resolved_at[:2] == (4.0, 4.0)


# --- whole games ------------------------------------------------------------------------------


def _log_counts(game, pattern):
    counts = Counter()
    for entry in game.log:
        match = re.match(pattern, entry.text)
        if match:
            counts[match.group(1)] += 1
    return counts


@pytest.mark.parametrize("kind", ["random", "greedy-path", "mix:baron,builder,targeted"])
@pytest.mark.parametrize("seed", [1, 2])
def test_recorded_game_agrees_with_the_final_state_and_the_log(kind, seed):
    game, summary = play_one(seed, 3, kind, RULES)
    metrics = summary.death_star
    assert metrics is not None
    assert metrics.contract_cubes + metrics.empire_cubes == game.death_star.cubes
    assert metrics.empire_cubes == game.stock_rounds_played * RULES.empire_cubes_per_stock_round
    assert metrics.stages_filled == game.death_star.stages_filled(RULES)
    assert metrics.stage_filled_at == metrics.stage_resolved_at
    assert list(metrics.stage_filled_at[: metrics.stages_filled]) == sorted(
        metrics.stage_filled_at[: metrics.stages_filled]
    )
    assert metrics.launched == game.death_star.launched
    assert sum(c.fleets_bought for c in metrics.corps.values()) == game.fleets_sold
    seized = _log_counts(game, r"^seizes a fleet from (\S+);")
    closed = {c.id for c in game.closed_corporations()}
    for corp in game.corporations.values():
        recorded = metrics.corps[corp.id]
        assert recorded.fleets_bought - recorded.fleets_seized == corp.fleets
        assert recorded.fleets_seized == seized[corp.id]
        assert recorded.closed == (corp.id in closed)
        assert recorded.contract_revenue <= recorded.revenue_total
    assert sorted(metrics.fleets_end_round) == list(range(1, game.round_number + 1))
    assert summary.rounds_played == game.round_number
    row = summary.to_row()
    assert row[f"{ROW_PREFIX}bankruptcies"] == len(closed)
    json.dumps(row)


def test_games_with_the_rules_off_have_no_death_star_fields():
    game, summary = play_one(1, 3, "greedy", DEFAULT_CONFIG)
    row = summary.to_row()
    assert summary.death_star is None
    assert not [k for k in row if k.startswith(ROW_PREFIX)]
    assert row["rounds_played"] == DEFAULT_CONFIG.total_rounds == game.round_number


# --- the report -------------------------------------------------------------------------------


def _rows(config, variant, seeds, bot="mix:baron,builder,targeted"):
    rows = []
    for seed in seeds:
        _, summary = play_one(seed, 3, bot, config)
        rows.append({"variant": variant, "player_count": 3, "bot": bot, "seed": seed})
        rows[-1].update(summary.to_row())
    return rows


def test_report_has_a_block_per_variant_and_the_death_star_lines_only_with_the_rules_on():
    rows = _rows(DEFAULT_CONFIG, "base", [1]) + _rows(RULES, "death_star", [1, 2])
    text = death_star_report(rows)
    base, death_star = text.split("\n\n")
    assert base.startswith("variant base: 1 games, Death Star rules off")
    assert "rounds played: mean 6.00" in base
    assert "stage" not in base
    assert death_star.startswith("variant death_star: 2 games, Death Star rules on")
    for phrase in [
        "ended by the station launching",
        "stage 1 (Frame)",
        "stage 4 (Completion)",
        "cubes per game",
        "fleets per corporation that operated",
        "bankruptcies per game",
        "near a seizure",
        "before a seizure or site move",
        "contract revenue",
    ]:
        assert phrase in death_star, phrase


def _closed_row(seat):
    """A minimal rules-on row in which CEC closed with ``seat`` as president."""
    row = {
        "variant": "v",
        "player_count": 3,
        "bot": "mix:baron,builder,targeted",
        "seed": 1,
        "rounds_played": 8,
        "shares_sold": 0,
        "corp.CEC.floated": False,
        "corp.CEC.withholds": 1,
        "corp.CEC.operating_turns": 4,
    }
    _, summary = play_one(1, 3, "random", RULES)
    assert summary.death_star is not None
    row.update({k: v for k, v in summary.death_star.to_row().items() if ".corp." not in k})
    for name, value in {
        "fleets_bought": 1,
        "fleet_spend": 60,
        "fleets_seized": 1,
        "final_fleets": 0,
        "contract_pairs": 0,
        "contract_revenue": 0,
        "revenue_total": 0,
        "closed": True,
        "closed_at": 9.0,
        "closed_round": 5,
        "closed_president": seat,
    }.items():
        row[f"{ROW_PREFIX}corp.CEC.{name}"] = value
    row[f"{ROW_PREFIX}bankruptcies"] = 1
    return row


def test_report_attributes_bankruptcies_to_the_presidents_strategy():
    text = variant_report("v", [_closed_row("P2"), _closed_row("P2")])
    assert "bankruptcies per game 1.00 (games with one: 100%); by round R5 2" in text
    builder = next(line for line in text.splitlines() if line.strip().startswith("builder"))
    assert builder.split() == ["builder", "2", "100.0"]
    assert "fleets per corporation that operated (2): bought 1.00" in text


def test_report_rejects_rows_mixing_rules_or_missing_rounds():
    on = _rows(RULES, "v", [1])
    off = _rows(DEFAULT_CONFIG, "v", [1])
    with pytest.raises(ValueError, match="mixes"):
        variant_report("v", on + off)
    del off[0]["rounds_played"]
    with pytest.raises(ValueError, match="rounds_played"):
        variant_report("v", off)


def test_death_star_report_command_filters_one_variant(tmp_path, capsys):
    rows = _rows(DEFAULT_CONFIG, "base", [1]) + _rows(RULES, "death_star", [1])
    path = tmp_path / "rows.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    args = argparse.Namespace(rows=path, variant="death_star")
    assert death_star_command(args) == 0
    out = capsys.readouterr().out
    assert out.startswith("variant death_star") and "variant base" not in out
    args.variant = "missing"
    assert death_star_command(args) == 2
