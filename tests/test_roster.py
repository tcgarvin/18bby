import pytest

from bby18.bots.roster import (
    DIFFICULTIES,
    PLANS,
    ROSTER,
    character_named,
    character_policy,
    roster_policy,
    draw_characters,
)
from bby18.bots.stable import STABLE
from bby18.config import BOT_NOISE, DIFFICULTY_TARGET_SHARE


def test_every_character_plays_a_stable_strategy_with_a_plan():
    assert all(c.strategy in STABLE and c.strategy in PLANS for c in ROSTER)


def test_character_names_are_unique_and_fit_a_seat():
    names = [c.name for c in ROSTER]
    assert len(names) == len(set(names))
    assert all(0 < len(n) <= 40 for n in names)


def test_every_difficulty_calibrates_every_roster_strategy():
    for difficulty in DIFFICULTIES:
        assert {c.strategy for c in ROSTER} <= set(BOT_NOISE[difficulty])


def test_difficulties_run_easiest_first_and_each_has_a_target():
    assert DIFFICULTIES == ("very-easy", "easy")
    assert set(DIFFICULTY_TARGET_SHARE) == set(DIFFICULTIES)
    shares = [DIFFICULTY_TARGET_SHARE[d] for d in DIFFICULTIES]
    assert shares == sorted(shares, reverse=True)


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


def test_characters_start_corporations_by_the_site_unless_their_strategy_starts_at_random():
    for strategy, policy in STABLE.items():
        expected = "random" if policy.start_order == "random" else "site"
        assert roster_policy(strategy).start_order == expected
    character = next(c for c in ROSTER if c.strategy == "baron")
    assert character_policy(character, DIFFICULTIES[0]).start_order == "site"
