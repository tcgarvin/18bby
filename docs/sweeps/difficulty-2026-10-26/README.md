# Easy opponents: noise recalibrated for the Death Star rules (2026-10-26)

The Death Star and fleets rules became the default on 2026-10-26 (contested sites within 4 hexes
of two homeworlds, 5 cubes per stage; see `docs/DECISIONS.md`). Every strategy plays a different
game under them, so `BOT_NOISE["easy"]` was recalibrated with the method of
`docs/sweeps/difficulty-2026-10-25` unchanged: the same target (`DIFFICULTY_TARGET_SHARE["easy"]`,
43% of the table's worth for the reference player), the same reference player (`builder`), the
same 13 roster strategies, noise levels, seat orders and maps. Only the rules differ: the specs'
`base` variant is `{}`, which now means the Death Star rules.

**Calibration** (`spec-easy.json`, 8,580 games: 13 strategies x 11 noise levels x 3 seat orders x
20 maps; `uv run python docs/sweeps/difficulty-2026-10-25/calibrate.py rows.jsonl 0.43`).
Reference share (%) by opponent noise:

| strategy | 0.0 | 0.3 | 0.5 | 0.7 | 0.9 | 1.0 | Easy noise | was |
|---|---|---|---|---|---|---|---|---|
| prestige | 30.8 | 34.2 | 38.5 | 42.5 | 47.7 | 49.3 | 0.72 | 0.72 |
| baron-prestige | 31.5 | 33.2 | 36.4 | 41.3 | 46.9 | 49.2 | 0.77 | 0.90 |
| early-builder | 32.2 | 36.5 | 39.6 | 42.8 | 47.3 | 50.3 | 0.71 | 0.89 |
| diversifier | 32.8 | 38.1 | 40.6 | 45.2 | 47.7 | 51.2 | 0.59 | 0.87 |
| baron | 33.0 | 38.2 | 40.0 | 44.7 | 47.9 | 51.9 | 0.62 | 0.95 |
| builder | 33.3 | 38.3 | 41.6 | 45.7 | 47.4 | 51.2 | 0.57 | 0.86 |
| targeted | 33.3 | 38.3 | 41.6 | 45.7 | 47.4 | 51.2 | 0.57 | 0.89 |
| hoarder | 33.3 | 38.3 | 41.6 | 45.7 | 47.4 | 51.2 | 0.57 | 0.69 |
| tycoon | 35.1 | 40.0 | 43.1 | 49.4 | 51.3 | 54.6 | 0.50 | 0.51 |
| spoiler | 35.9 | 40.1 | 43.7 | 46.9 | 48.2 | 50.9 | 0.46 | 0.63 |
| baron-tycoon | 36.2 | 39.1 | 42.8 | 47.1 | 51.4 | 53.2 | 0.51 | 0.86 |
| straight | 37.8 | 42.0 | 45.0 | 49.7 | 51.4 | 55.9 | 0.35 | 0.29 |
| churner | 38.7 | 42.5 | 46.6 | 49.0 | 54.6 | 57.9 | 0.33 | 0.40 |

The largest standard error of a cell is 1.7 points. Every strategy reaches the target below noise
1.0, so none is capped.

**Check on fresh maps** (`spec-easy-check.json`, maps 101-130, 90 games per strategy at the new
noise): the reference player takes 40.5% (spoiler) to 43.7% (tycoon), 42.2% overall (standard
error of one strategy about 0.9 points). The 2026-10-25 calibration gave 42.6% overall on the same
maps under the old rules.

**What changed and why.**

- **Less noise is needed.** Noise costs a bot more under the Death Star rules, most likely
  because a careless build or dividend can leave a corporation short of the cash for its fleets
  (not measured separately). At noise 1.0 the reference player now takes 49-58% (about 45%
  before), and the strongest strategies reach 43% at noise 0.6-0.8 instead of about 0.9. Easy
  bots therefore play their plan more faithfully than before.
- **The strategies are closer together at noise 0** (30.8-38.7% against 27.7-40.1%): the dividend
  knobs that separated the baron family from the rest probably matter less once keeping the
  fleet reserve decides many dividends.
- **builder, targeted and hoarder play identically** under these rules: all 1,320 of their games
  here have the same worths, seat for seat. Under the Death Star rules the bot's dividend decision
  (`GreedyBot._intended_death_star_dividend`) withholds for the fleet reserve and otherwise pays
  unless the cash would buy something, which overrides what distinguishes the three. Their
  characters are distinct in name only, and the plan revealed at the end of the game ("keep cash in
  the treasury and pay only when flush", "pay dividends unless the company needed the cash for a
  build") describes knobs that did not change play. Not fixed here: it is a strategy change, not a
  calibration one.

The caveat of the first calibration still applies, more mildly: at Easy the strongest strategies
play with noise near 0.6-0.8, so the revealed strategy describes the plan the bot was following, not
how well it followed it.
