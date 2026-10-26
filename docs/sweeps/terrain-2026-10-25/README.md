# Terrain and 70-credit upgrade: sweep results (2026-10-25)

> **Note (2026-10-26).** These specs were run when an empty variant (`{}`) meant the rules without
> the Death Star, which became the default on 2026-10-26. To rerun them under the rules they
> measured, add `"death_star_rules": false` to each variant (`CLASSIC_CONFIG` in `config.py`).

Question: after adding asteroid fields and nebulae (15% / 15% of non-planet hexes), a 30-credit
nebula chart surcharge, a ban on upgrading nebula tiles, and a 70-credit 2-to-3-exit upgrade
(was 50), do planets change in value, are planets that used to be linked now left out, and are
players forced to choose?

Short answer: **yes, measurably, but the effect is mild at 15% / 15%.** Terrain makes each planet's
value depend on the sky and makes each game a different puzzle. It does not yet make players
leave much of the map unlinked, because the two-action turn limit, not terrain or cash, is
what decides how much of the map a corporation can reach.

## What was run

All games: 3 players, seeds 1-300 per cell, no failures. Files here:

| File | What |
|---|---|
| `spec1.json` | 10,800 games: 9 variants x 3 and 4 players x 2 bots (first sweep; planet value in it used the older removal-based metric and is not quoted below) |
| `spec2.json` | 6,600 games: 11 variants x 3 players x 2 bots. **All numbers below come from this sweep** |
| `analyze.py` | per-variant tables from a results JSONL: `python analyze.py rows.jsonl old` |
| `seedcorr.py` | within-planet link between a planet's access cost in a seed and its reach in that game |
| `upgrade_probe.py` | does the path bot ever want an upgrade, with and without a cost tie-break? |
| `static_grid.py` | map-only terrain density grid (`bby18 terrain-report` is the same measurement) |

Variants: `old` = previous rules (upgrade 50, no terrain). `cost70` = upgrade 70 only. `terrain` =
15/15 terrain only. `new` = both (the adopted rules). `patch5` = patches up to 5 hexes.
`dense` = 25% / 25%. `heavy` = 35% asteroids, 20% nebula, patches up to 5. `up60`, `up90` =
upgrade cost. `act1`, `act3` = one or three network actions per turn.

Bots: `greedy-path` (new) prices routes around terrain and picks tile exits toward its target;
`greedy` (original) measures straight-line hexes and picks exits at random. Treat `greedy-path` as
the better stand-in for a thoughtful player. The two agree on direction nearly everywhere; where
they disagree it is noted.

## 1. Do planets become more or less valuable?

**Yes: a planet's value now depends on the sky.** For each planet in each game I took its
*access cost* in that seed (average cheapest build cost to its three nearest planets, from the map
alone) and compared it with how many corporations reached the planet and how much revenue it
earned, after removing each planet's average (so the fixed geography of the board cancels out).

| Rules | r(access cost, corporations reaching) | Slope per +50 credits of access cost | Revenue per planet per +50 |
|---|---|---|---|
| `old` (no terrain; control) | +0.02 | +0.03 corps | +0.7 credits |
| `new` (15/15) | -0.38 | -0.88 corps | -17 credits |
| `dense` (25/25) | -0.48 | -0.91 corps | -17 credits |
| `heavy` | -0.49 | -0.76 corps | -15 credits |

(`greedy-path`; `greedy` gives -0.29 / -0.68 / -13 at 15/15.) The control row is the point: with no
terrain the sky means nothing, with terrain a planet that is 50 credits harder to reach in that
game is reached by about 0.9 fewer of the 3 corporations.

**Map-only view** (`bby18 terrain-report`, 150 seeds, pairs that link for under 150 on an empty
sky): at 15/15 only 23% of those pairs get costlier, by 13 credits on average. At 25/25, 48% do
(+37). Asteroids matter more than nebulae (15% asteroids alone: 10% of pairs, +8; 15% nebula alone:
10%, +3). Patches of up to 5 hexes hurt more than scattered single hexes (+18 vs +8).

**Games differ from each other more.** Standard deviation, across games, of the average planets a
corporation reaches: `old` 0.35, `new` 0.68, `dense` 1.24, `heavy` 2.11 (`greedy`: 0.48, 1.41,
2.78, 3.44). The sky now explains a large share of how a game goes.

No planet is reliably the big winner or loser: which planets lose reach differs between bots
(Mon Cala, Kashyyyk and Eriadu for `greedy-path`; Dantooine, Felucia and Lothal for `greedy`), so
per-planet rankings are noise. Aggregate inequality of planet value (Gini) barely moves
(0.20 -> 0.22 for `greedy-path`, 0.28 -> 0.26 for `greedy`), so terrain does not create
"rich" and "poor" planets on average, it makes them vary by seed.

## 2. Are planets that were normally linked now left unlinked?

Slightly. `greedy-path`, 3 players, end of game:

| Variant | Planets per corporation (of 24) | Planets reached by any corporation | Near pairs with an unreached planet | Unreached planets within 150 credits, per corporation |
|---|---|---|---|---|
| `old` | 21.3 | 98% | 2% | 2.7 |
| `cost70` | 20.9 | 97% | 3% | 3.1 |
| `terrain` | 21.0 | 96% | 4% | 2.8 |
| `new` | 20.7 | 95% | 5% | 3.1 |
| `dense` | 20.0 | 90% | 12% | 3.3 |
| `heavy` | 19.0 | 87% | 17% | 2.9 |

("Near pair" = two planets within three hexes.) At the adopted settings stranded near pairs go from
2% to 5% of pairs, planets per corporation fall about half a planet, and final revenue falls 3%
(409 to 397). That is a real, consistent shift but a small one. The original `greedy` bot agrees
that each corporation reaches fewer planets (19.6 -> 19.3) but not that coverage falls: planets
reached by any corporation go 90% -> 92% and stranded near pairs 10% -> 9%. Its random exits
already leave about a tenth of the map unreached, and I have not established why terrain helps it.

## 3. Are players making choices?

The budget decides, not terrain. The network-action limit is the lever that actually creates scarcity:

| Network actions per turn | Planets per corporation | Reached by any corp | Unreached within 150 credits |
|---|---|---|---|
| 1 | 12.5 | 69% | 9.5 per corporation |
| 2 (current) | 20.7 | 95% | 3.1 |
| 3 | 24.0 | 100% | 0.0 |

(`greedy-path`, `new` rules.) At two actions a corporation already reaches 21 of 24 planets, and it
still ends the game holding about 340 credits it never spent (390-400 before terrain). Cash does
not bind, so the 50/70/80 prices change *which* builds happen, not *how many*.

What terrain does change in play: corporations pay the nebula surcharge about 0.55 times each
(1.4 at 25/25), service riding on others' tiles rises (18 to 21 shared tiles), and about one extra
planet per corporation is left within easy reach (2.7 -> 3.1). Those are small, but they are
decisions about *where* to spend a scarce action, not whether to.

## 4. The 70-credit upgrade is nearly dead

Planets are open hubs, so a line can already branch at any planet. `greedy-path` upgrades a tile
0.67 times per corporation at 50 credits, 0.06 at 60, 0.06 at 70 and 0.03 at 90 (junction tiles
2.0 -> 0.2). `upgrade_probe.py` shows why: when the bot ignores cost, it upgrades about 0.65 times
per corporation *at any price* (30, 50, 70), so about two corporations in three find an upgrade
strictly best. Those upgrades are worth about 5 revenue and 0.25 planets per corporation, the
whole price of skipping them. So 70 is "never worth it" for a price-sensitive player and the
2-to-3-exit decision does not become a deliberate trade-off. The original `greedy` bot picks
upgrades largely at random and still makes 4.3 per corporation at 70 (5.5 at 50).

If the intent is that the upgrade should be a real choice, the price is not the lever: the upgrade
has to buy something a new tile cannot (for example, a hub that several corporations can use, or a
junction bonus).

## 5. Side effects worth knowing

- Players end poorer: `greedy-path` mean final worth 3863 -> 3638 (-6%): -4% from the 70 upgrade
  alone, -3% from terrain alone.
- The pre-existing seat skew did not move for the better. Seat 3 almost never wins (1% for the path
  bot before and after), and seat 1's share rose from 49% to 65% under the new rules with the path
  bot (32% from 44% with the original bot, the other direction). This sweep was not designed to
  explain that.
- Caveat: the bots are not players. `greedy-path` is a sensible router but never plans more than
  one action ahead, ignores rivals' likely moves and does not weigh nebula tolls against detours
  except by cost, so it probably under-uses detours and over-uses straight lines. Treat absolute
  numbers as bot-conditional; the within-planet correlation and the control comparison are the
  more trustworthy evidence.

## Suggested next steps

1. If the goal is "I must give things up": raise terrain to roughly 25% / 25% (coverage 90%, 12%
   of near pairs stranded) or tighten the action budget. One action per turn is far too tight;
   two actions with heavier terrain is closer. A middle step, such as 2 actions on turns when
   a corporation has under some treasury, is a design question for you.
2. Decide what the 2-to-3-exit upgrade is for, then price it (section 4).
3. Seat skew (seat 3 near zero) predates this change and deserves its own look.
