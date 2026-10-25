"""The strategy stable: named ``GreedyPolicy`` archetypes, each a coherent plan a player might
follow, for tournaments that look for dominant strategies (see ``bby18.tournament``).

Every archetype except ``straight`` prices routes around terrain, so they differ in plan rather
than in building skill. ``straight`` is the bot the web app seats, kept as a reference. Adding a
strategy is one entry here; it becomes a bot kind for playtests and sweeps.
"""

from __future__ import annotations

from bby18.bots.greedy import GreedyPolicy

STABLE: dict[str, GreedyPolicy] = {
    # Dividends.
    "baron": GreedyPolicy(routing="path", pay_threshold=0),
    "builder": GreedyPolicy(routing="path"),
    "early-builder": GreedyPolicy(routing="path", withhold_until_round=2, pay_threshold=0),
    "targeted": GreedyPolicy(routing="path", withhold_for_builds=True),
    "hoarder": GreedyPolicy(routing="path", pay_threshold=4),
    # Starting corporations.
    "investor": GreedyPolicy(routing="path", max_presidencies=0, sell_losers=True),
    "tycoon": GreedyPolicy(
        routing="path", max_presidencies=2, start_order="best_home", last_start_round=2
    ),
    "prestige": GreedyPolicy(routing="path", par_choice="max"),
    # Always-pay combined with the starting plans, to separate the two axes.
    "baron-tycoon": GreedyPolicy(
        routing="path",
        pay_threshold=0,
        max_presidencies=2,
        start_order="best_home",
        last_start_round=2,
    ),
    "baron-prestige": GreedyPolicy(routing="path", pay_threshold=0, par_choice="max"),
    # Share trading. (A "loyalist" with a larger own-share bonus plays identically to
    # builder: the default bot already buys its own corporation whenever it can.)
    "diversifier": GreedyPolicy(routing="path", own_share_bonus=0.67),
    "churner": GreedyPolicy(routing="path", sell_losers=True, start_order="random"),
    "spoiler": GreedyPolicy(routing="path", dump_rivals=True),
    # Reference: the bot the web app seats.
    "straight": GreedyPolicy(),
}
"""Archetype name -> policy. Names must not contain commas (they go in ``mix:`` strings)."""
