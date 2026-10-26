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

| strategy | 0.0 | 0.3 | 0.5 | 0.7 | 0.9 | 1.0 | Easy noise | first 2026-10-26 run |
|---|---|---|---|---|---|---|---|---|
| baron-prestige | 27.9 | 30.1 | 33.3 | 36.7 | 43.7 | 45.3 | 0.88 | 0.77 |
| early-builder | 28.5 | 32.5 | 37.0 | 40.2 | 44.6 | 47.8 | 0.83 | 0.71 |
| targeted | 28.6 | 36.0 | 40.5 | 42.1 | 45.9 | 48.3 | 0.74 | 0.57 |
| prestige | 29.7 | 34.7 | 37.1 | 41.0 | 43.1 | 45.2 | 0.80 | 0.72 |
| baron | 30.5 | 34.6 | 37.0 | 41.0 | 45.7 | 49.0 | 0.81 | 0.62 |
| diversifier | 32.8 | 37.4 | 39.2 | 42.9 | 46.6 | 49.2 | 0.71 | 0.59 |
| builder | 33.3 | 38.7 | 41.8 | 43.8 | 46.4 | 49.2 | 0.65 | 0.57 |
| baron-tycoon | 34.8 | 36.8 | 38.4 | 45.7 | 48.3 | 52.5 | 0.62 | 0.51 |
| spoiler | 35.9 | 41.2 | 45.0 | 45.8 | 46.7 | 49.1 | 0.39 | 0.46 |
| hoarder | 37.7 | 41.7 | 45.1 | 45.4 | 47.8 | 48.0 | 0.33 | 0.57 |
| tycoon | 37.8 | 39.9 | 42.4 | 47.5 | 49.5 | 51.3 | 0.52 | 0.50 |
| straight | 41.1 | 44.4 | 46.2 | 49.1 | 51.4 | 53.1 | 0.20 | 0.35 |
| churner | 42.6 | 45.5 | 50.2 | 51.9 | 53.6 | 54.9 | 0.03 | 0.33 |

The largest standard error of a cell is 1.9 points. Every strategy reaches the target below noise
1.0, so none is capped. Churner gives the reference player 42.6% at noise 0, so it plays Easy almost
noise-free.

**Check on fresh maps** (`spec-easy-check.json`, maps 101-130, 90 games per strategy at the new
noise): the reference player takes 39.9% (spoiler) to 44.5% (tycoon), 42.2% overall (standard
error of one strategy about 1.2 points). The 2026-10-25 calibration gave 42.6% overall on the same
maps under the old rules.

**Rerun after a bot fix (2026-10-26).** builder, targeted and hoarder were made distinct under the
Death Star rules (and the re-fleet reserve now allows 4 cubes of margin, not 2, which ended the
always-pay bots' accidental bankruptcies), so every strategy, the reference player included, plays
differently and the calibration above was rerun with the same specs; the table replaces the first
run's.

**What changed and why.**

- **Noise matters more than under the old rules.** At noise 1.0 the reference player takes
  45-55% (about 45% before), probably because a careless build or dividend can leave a corporation
  short of the cash for its fleets (not measured separately). The strongest strategies reach 43%
  at noise 0.8-0.9, as under the old rules.
- **The spread at noise 0 is about as wide as under the old rules** (27.9-42.6% against
  27.7-40.1%). The pay-when-short strategies (builder's cushion, hoarder, straight, churner,
  tycoon, spoiler) withhold more now that their cushion binds, which makes them easier opponents.
- **builder, targeted and hoarder now differ.** In the first run they played identical games (all
  1,320 of theirs had the same worths): below its `pay_threshold` cushion a corporation withheld
  only when a single build or fleet cost more than its whole treasury, which is exactly
  `targeted`'s rule, and above the cushion (120 or more) nothing it wanted ever cost more, so it
  paid as `targeted` did. Now builder and hoarder withhold below two or four charts' worth of spendable cash
  while a revenue-raising planet lies within what that cushion would pay to reach, and targeted
  withholds only for a revenue-raising build (or wanted fleet) it cannot afford.

The caveat of the first calibration still applies: at Easy the strongest strategies
play with noise near 0.8-0.9, so the revealed strategy describes the plan the bot was following, not
how well it followed it.
