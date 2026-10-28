"""Named opponents for the web app: each character plays one stable strategy at a difficulty.

A player picks a difficulty, not a strategy; bot seats are filled with characters drawn from the
game seed, so a saved game rebuilds with the same opponents. The strategy is revealed when the
game ends. A character's carelessness at each difficulty comes from ``BOT_NOISE`` in
``config.py``, calibrated per strategy so every character at one difficulty is about equally hard
to beat (see ``docs/sweeps/difficulty-2026-10-28``). Characters start corporations by
the Death Star site (``roster_policy``).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from bby18.bots.greedy import GreedyPolicy
from bby18.bots.stable import STABLE
from bby18.config import BOT_NOISE

DIFFICULTIES = tuple(BOT_NOISE)
"""Difficulties the web app offers, easiest first."""


@dataclass(frozen=True)
class Character:
    name: str
    strategy: str
    """A key of ``STABLE``."""


ROSTER: tuple[Character, ...] = (
    Character("Gloop Shitto", "baron"),
    Character("Grumbo Fesk", "baron"),
    Character("Lussa Vrell", "baron"),
    Character("Zebbo Nackt", "targeted"),
    Character("Mox Tarravin", "targeted"),
    Character("Snivvel Krake", "targeted"),
    Character("Ooma Tib", "baron-prestige"),
    Character("Drusk Malvane", "baron-prestige"),
    Character("Teeza Orrum", "baron-prestige"),
    Character("Sloomo Drex", "early-builder"),
    Character("Vex Corrabin", "early-builder"),
    Character("Nubb Glunda", "early-builder"),
    Character("Pilly Wanz", "baron-tycoon"),
    Character("Korbo Ghast", "baron-tycoon"),
    Character("Hessa Quoon", "baron-tycoon"),
    Character("Bolo Tarrk", "builder"),
    Character("Yinna Sorrow", "builder"),
    Character("Fennick Dorr", "builder"),
    Character("Ardo Phlegg", "prestige"),
    Character("Marisol Venn", "prestige"),
    Character("Quill Abbadax", "prestige"),
    Character("Ruskin Toob", "spoiler"),
    Character("Selka Darrow", "spoiler"),
    Character("Gribbo Mook", "spoiler"),
    Character("Wenna Krill", "tycoon"),
    Character("Dobbs Ulvane", "tycoon"),
    Character("Tarla Mung", "tycoon"),
    Character("Pom Grizzek", "hoarder"),
    Character("Ulla Vant", "hoarder"),
    Character("Kezzer Hobb", "hoarder"),
    Character("Ibbit Sallow", "churner"),
    Character("Rhonn Fazzle", "churner"),
    Character("Nissa Throope", "churner"),
    Character("Blunt Ovaro", "diversifier"),
    Character("Mabbet Rook", "diversifier"),
    Character("Zuggo Plint", "diversifier"),
    Character("Orrin Kessel-Vay", "straight"),
    Character("Duna Spleck", "straight"),
    Character("Hobb Jarrow", "straight"),
)
"""Every character. Investor is left out: two investors leave a human running every company."""

PLANS: dict[str, str] = {
    "baron": "pay every dividend",
    "targeted": "pay dividends unless the company needed the cash for a build",
    "baron-prestige": "start at a high par and pay every dividend",
    "early-builder": "hold back dividends for two rounds to build, then pay everything",
    "baron-tycoon": "run two cheap companies and pay every dividend",
    "builder": "pay dividends once the treasury could cover two builds",
    "prestige": "start at the highest par it could float alone",
    "spoiler": "sell shares in the leader's company to drag its price down",
    "tycoon": "run two cheap companies",
    "hoarder": "keep cash in the treasury and pay only when flush",
    "churner": "sell any share that fell below par",
    "diversifier": "float its own company, then buy other players' companies rather than its own",
    "straight": "plan routes in straight lines, ignoring terrain",
    "investor": "never run a company, only buy shares",
}
"""A plain description of each strategy, revealed at the end of a game."""


def character_named(name: str) -> Character:
    for character in ROSTER:
        if character.name == name:
            return character
    raise KeyError(f"No character named {name!r}")


ROSTER_START_ORDER = "site"
"""How characters choose what to start, unless their strategy starts at random: like a person
at the table, they weigh where the Death Star is (``GreedyPolicy.start_order``)."""


def roster_policy(strategy: str) -> GreedyPolicy:
    """The stable strategy as characters play it, before any noise: the stable as tournaments
    seat it, but starting corporations by ``ROSTER_START_ORDER`` (bot kind ``strategy@site``)."""
    policy = STABLE[strategy]
    if policy.start_order == "random":
        return policy
    return replace(policy, start_order=ROSTER_START_ORDER)


def character_policy(character: Character, difficulty: str) -> GreedyPolicy:
    """The policy ``character`` plays at ``difficulty``."""
    if difficulty not in BOT_NOISE:
        raise ValueError(f"Unknown difficulty {difficulty!r}; choose from {DIFFICULTIES}")
    return replace(
        roster_policy(character.strategy), noise=BOT_NOISE[difficulty][character.strategy]
    )


def draw_characters(seed: int, count: int) -> list[Character]:
    """``count`` distinct characters for a game, fixed by its seed."""
    if count > len(ROSTER):
        raise ValueError(f"Only {len(ROSTER)} characters exist")
    return random.Random(f"characters:{seed}").sample(ROSTER, count)
