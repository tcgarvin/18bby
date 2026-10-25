import pytest

from bby18.bots.roster import (
    DIFFICULTIES,
    PLANS,
    ROSTER,
    character_named,
    character_policy,
    draw_characters,
)
from bby18.bots.stable import STABLE
from bby18.config import BOT_NOISE


def test_every_character_plays_a_stable_strategy_with_a_plan():
    assert all(c.strategy in STABLE and c.strategy in PLANS for c in ROSTER)


def test_character_names_are_unique_and_fit_a_seat():
    names = [c.name for c in ROSTER]
    assert len(names) == len(set(names))
    assert all(0 < len(n) <= 40 for n in names)


def test_every_difficulty_calibrates_every_roster_strategy():
    for difficulty in DIFFICULTIES:
        assert {c.strategy for c in ROSTER} <= set(BOT_NOISE[difficulty])


def test_character_policy_is_the_strategy_with_its_noise():
    character = ROSTER[0]
    policy = character_policy(character, "easy")
    assert policy.noise == BOT_NOISE["easy"][character.strategy]
    assert policy.pay_threshold == STABLE[character.strategy].pay_threshold


def test_unknown_difficulty_and_name_are_rejected():
    with pytest.raises(ValueError):
        character_policy(ROSTER[0], "brutal")
    with pytest.raises(KeyError):
        character_named("Nobody")


def test_draw_is_distinct_and_fixed_by_seed():
    drawn = draw_characters(7, 3)
    assert len({c.name for c in drawn}) == 3
    assert drawn == draw_characters(7, 3)
