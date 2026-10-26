"""The strategy stable: named ``GreedyPolicy`` archetypes, each a coherent plan a player might
follow, for tournaments that look for dominant strategies (see ``bby18.tournament``).

Every archetype except ``straight`` prices routes around terrain, so they differ in plan rather
than in building skill. ``straight`` is the bot the web app seats, kept as a reference. Adding a
strategy is one entry here; it becomes a bot kind for playtests and sweeps.

Under the experimental Death Star rules every archetype also plays the fleet game competently
(see ``GreedyBot``): it keeps a replacement fleet's price against seizures, buys fleets by value
and builds for the pairs its fleets can run. The last group of archetypes differ only in fleet
and contract plans, so with the rules off they play like the archetype they are built on. The
Death Star tournament should use baron, saver, admiral, contractor, staller, raider, targeted,
early-builder, investor, baron-tycoon, baron-prestige and builder.
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
    # Fleet and contract plans (they matter only under the Death Star rules).
    "admiral": GreedyPolicy(
        # Buy cheap fleets early, pushing rivals into dearer tiers; withhold the first round.
        routing="path",
        fleet_target=4,
        withhold_until_round=1,
        pay_threshold=0,
    ),
    "contractor": GreedyPolicy(
        # Rush the construction site, pay everything, end the game while ahead.
        routing="path",
        contract_weight=2.0,
        pay_threshold=0,
        fleet_payback_turns=2.0,
    ),
    "staller": GreedyPolicy(
        # Never build toward the site; play for the long game.
        routing="path",
        contract_weight=0.0,
        withhold_for_builds=True,
    ),
    "saver": GreedyPolicy(
        # Pay everything it can while keeping two fleets' worth in the treasury.
        routing="path",
        pay_threshold=0,
        treasury_reserve_fleets=2.0,
    ),
    "raider": GreedyPolicy(
        # Abuse probe: one fleet, pay everything, dump its own shares before a seizure.
        routing="path",
        fleet_target=1,
        pay_threshold=0,
        sell_own_before_seizure=True,
    ),
}
"""Archetype name -> policy. Names must not contain commas (they go in ``mix:`` strings)."""
