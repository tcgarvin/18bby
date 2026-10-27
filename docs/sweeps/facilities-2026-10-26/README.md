# Facilities and planet exits: sweep results (2026-10-26)

Question: the designer found lane placement dull ("just connect two places"; upgraded lanes almost
never used). Under the fleet rules a corporation builds to its eight scoring planets and stops: in
bot games it passed its network actions on about 12 of its 15 operating turns, upgraded 0.04 times
a game and left half the planets untouched. The designer proposed facilities on planets in place
of fleets: each facility adds an exit to its planet (planets start with one) and one pair of
capacity, and the Empire takes facilities over instead of fleets. Rules as built: "Facilities and
planet exits" in `docs/DECISIONS.md`. Fable consulted on the design and on these results.

Do facilities make lanes and upgrades matter, and do they keep the strategy balance the fleet
rules reached?

## Method

The stable tournament as in `docs/sweeps/map-2026-10-26`: 3 players, the 8 strategies that carry
the equilibrium (admiral, early-builder, targeted, baron, contractor, baron-prestige, staller,
builder), every lineup in every seat order, maps 1-20: 10,240 games per variant. Bots price planet
exits in their routes (`src/bby18/bots/routing.py`) and value a facility's exit as well as its
pair (`_choose_facility` in `greedy.py`). `fleet_target` counts facilities, the free home one
included, so `admiral` owns four.

| file | what |
|---|---|
| `spec-tournament.json` | fleets vs facilities as ruled |
| `spec-tuning.json`, `spec-tuning2.json` | tuning variants (below) |
| `report-tournament-*.txt`, `report-tuning-*.txt` | `bby18 tournament-report` per variant |
| `dsreport-*.txt` | `bby18 death-star-report`: clock, facilities, exits, late actions |
| `spec-bots.json`, `dsreport-bots-*.txt` | 60-game bot checks while the bots were taught exits |

## Results

### The lane game

| per corporation per game | fleets | facilities |
|---|---|---|
| upgrades (3-exit tiles) | 0.09 | **0.73** |
| network actions (from round 5 on) | 7.66 (1.03) | 8.50 (1.13) |
| planets reached at the end | 6.97 | 7.04 |
| planets touched by any lane, per game | 13.4 of 24 | 11.4 of 24 |

Upgraded lanes become a regular part of play: about eight times as many. The control variant
with **two** base exits per planet (`fac-base2`) drops upgrades back to 0.17, so the single base
exit is what does it. Late building barely moves (1.13 against 1.03 actions from round 5): slots
are not scarce (about 7 corporate and 4 Imperial facilities fill 48 slots), so a seized facility is
replaced on a planet already reached, with no new lane.

Facilities' new exits: 98% are left unclaimed by the builder, but most are then claimed by the
next lane charted toward the planet; only about 3 facility exits a game are never used. Bots never
charted a lane toward a full planet to have a facility connect it (dangling lanes at game end:
0.0), so the gift-to-a-dangling-lane rule is untested by the bots.

### Strategy balance

| variant | change from facilities as ruled | equilibrium | viable (bootstrap mean, min-max) | launch | bankruptcies/game |
|---|---|---|---|---|---|
| fleets | the current rules | early-builder 54, admiral 25, baron 21 | 2.1 (1-3) | 37% | 0.00 |
| facilities | as ruled | admiral 100 *or* baron 100 | 1.3 (1-3) | 25% | 0.01 |
| fac-t3 | first tier 3 at 60 | baron 62, admiral 38 | 1.7 (1-2) | 21% | 0.01 |
| fac-t333 | tiers 3@60, 3@90, 6@120 | admiral 100 | 1.1 (1-2) | 22% | 0.02 |
| fac-t90 | no 60 tier | baron 100 | 1.0 | 20% | 0.03 |
| fac-c4 | 4 cubes per stage | admiral 100 | 1.1 (1-2) | 28% | 0.02 |
| fac-t3-c4 | both | admiral 93, baron 7 | 1.5 (1-2) | 25% | 0.02 |
| fac-emp2 | Empire adds 2 cubes per stock round | admiral 100 | 1.0 | 39% | 0.00 |
| **fac-limit3** | **limit 3 facilities** | **staller 71, baron 29** | **2.0 (1-4)** | 26% | 0.00 |
| fac-slots1 | 1 facility per planet | admiral 45, baron-prestige 38, staller 18 | 2.3 (1-4) | 22% | **0.46** |
| fac-base2 | 2 base exits (control) | admiral 100 | 1.0 | 38% | 0.00 |
| fac-combo | no 60 tier, 1 slot, Empire 2 | admiral 74, baron-prestige 26 | 1.8 (1-2) | 42% | **0.96** |

Why admiral and baron take over as ruled (Fable's reading, consistent with the numbers): capacity
got cheaper and the decline weaker. The free home facilities sit outside the supply, so only about
8 facilities are sold a game against 11 fleets and the price at the end is tier 2 in 94% of games
(fleets: tier 3 in 41%). Buying to four at 60-90 pays for itself, and nothing invades admiral.
Contracts fall (7.9 cubes a game to 5.8: the site is harder to reach through one-exit planets), so
the station launches less, there are fewer seizures and less decline, and always-pay wins.

A limit of three facilities is the one change that restores balance without side effects. One
slot per planet balances better still but bankrupts a corporation in a third of games: it runs out
of planets with a free slot it may build on, and closes with money in the treasury.

### Combinations with the limit of three (`spec-tuning3.json`)

| variant | change from facilities as ruled | equilibrium | viable (bootstrap mean, min-max) | launch | bankruptcies/game | contract share of revenue |
|---|---|---|---|---|---|---|
| **l3-emp2** | **limit 3, Empire 2 cubes per stock round** | **admiral 65, staller 26, contractor 9** | **2.6 (2-3)** | 37% | 0.00 | 4.8% |
| l3-c4 | limit 3, 4 cubes per stage | staller 68, admiral 32 | 1.8 (1-3) | 28% | 0.01 | 7.3% |
| l3-slots1 | limit 3, 1 slot per planet | admiral 63, staller 37 | 2.1 (1-3) | 22% | 0.44 | 10.2% |
| l3-t3 | limit 3, first tier 3 at 60 | admiral 100 | 1.0 (1-2) | 21% | 0.00 | 8.4% |
| limit2 | limit 2 | baron 100 | 1.0 | 16% | 0.00 | 8.9% |

`l3-emp2` keeps the most strategies (every resample keeps at least two; fleets: minimum one) and
the station launches as often as under fleets. But admiral is the best response to 28 of 36
opponent sets, and the Empire now builds most of the station (15 Empire cubes a game against 2.6
from contracts), so contracts are 4.8% of revenue (fleets: 11.6%) and the site stops mattering as
a destination: the station becomes a timer.

### Richer contracts instead of a faster Empire (`spec-tuning4.json`)

| variant | change from facilities as ruled | equilibrium | viable (bootstrap mean, min-max) | launch | contract share | best responses |
|---|---|---|---|---|---|---|
| **l3-rich** | **limit 3, contracts 50/60/70/80** | **staller 61, baron 39** | **2.2 (1-4)** | 27% | 10.9% | admiral 14, baron 10, contractor 5, targeted 5, staller 2 |
| l3-rich-c4 | the same, 4 cubes per stage | staller 67, admiral 33 | 1.8 (1-4) | 29% | 8.8% | admiral 16, baron 12, staller 5, contractor 3 |

`l3-rich` keeps contracts as large a part of revenue as under fleets and spreads best responses
widest of any variant: no strategy is the best answer to more than 14 of the 36 opponent sets.
Under fleets, rich contracts (60-90) handed the game to site-rushers (2026-10-25); here the
one-exit planets make the site harder to reach, so the richer contract is what restores it.

### Fresh maps (21-40)

| variant | equilibrium | viable (bootstrap mean, min-max) | launch | contract share |
|---|---|---|---|---|
| fleets | baron 82, admiral 18 | 2.3 (2-4) | 20% | 7.1% |
| l3-emp2 | admiral 42, contractor 38, staller 20 | 2.6 (1-3) | 30% | 3.6% |
| l3-rich | baron 53, staller 47 | 2.0 (1-3) | 12% | 6.9% |

On the fresh maps `l3-rich` again spreads best responses (admiral 13, baron 10, targeted 6,
contractor 5, staller 2 of 36) and has no bankruptcies; upgrades 0.68 per corporation.

## Decision (2026-10-27)

**Adopted: `l3-rich`**, facilities with a limit of three per corporation and contracts at
50/60/70/80. It matches the fleet rules' balance on both map sets (bootstrap 2.2 and 2.0 viable
strategies against 2.1 and 2.3), spreads best responses wider than either fleets or `l3-emp2`,
keeps contracts as large a part of revenue as under fleets, and makes upgraded lanes routine (about
0.7 per corporation against under 0.1).

**Weak spots to watch in play:**
- The station launches less often (27% and 12% of games against fleets' 37% and 20%); most games
  end at the round-8 backstop.
- Late-game building did not come back: 0.86 network actions per corporation from round 5 on,
  against 1.03 under fleets. Slots are not scarce enough to force new lanes after a seizure.
- Bots never chart toward a full planet to have a facility connect the lane later, so the "give
  the new exit to a dangling lane" rule is untested by them.

**The alternative** is `l3-emp2` (the Empire adds 2 cubes per stock round instead of richer
contracts). It keeps more strategies alive, but admiral is the best response to most opponent sets,
and the Empire builds most of the station, so contracts fade to 4% of revenue.
