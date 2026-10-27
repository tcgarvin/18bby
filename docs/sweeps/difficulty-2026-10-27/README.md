# Easy opponents: noise recalibrated for the facility rules (2026-10-27)

The facility rules became the default on 2026-10-27 (facilities and planet exits in place of
fleets, at most 3 facilities per corporation, contracts at 50/60/70/80; see "Facilities and
planet exits" in `docs/DECISIONS.md` and `docs/sweeps/facilities-2026-10-26`). Every strategy
plays a different game under them, so `BOT_NOISE["easy"]` was recalibrated with the method of
`docs/sweeps/difficulty-2026-10-25` unchanged: the same target (`DIFFICULTY_TARGET_SHARE["easy"]`,
43% of the table's worth for the reference player), the same reference player (`builder`), the
same 13 roster strategies, noise levels, seat orders and maps. Only the rules differ: the specs
are those of `docs/sweeps/map-2026-10-26`, whose `base` variant `{}` now means the facility rules.

**Calibration** (`spec-easy.json`, 8,580 games: 13 strategies x 11 noise levels x 3 seat orders x
20 maps; `uv run python docs/sweeps/difficulty-2026-10-25/calibrate.py rows.jsonl 0.43`).
Reference share (%) by opponent noise:

| strategy | 0.0 | 0.3 | 0.5 | 0.7 | 0.9 | 1.0 | Easy noise | fleet rules (2026-10-26) |
|---|---|---|---|---|---|---|---|---|
| targeted | 27.8 | 32.6 | 34.6 | 40.2 | 43.5 | 45.5 | 0.86 | 0.68 |
| baron | 29.3 | 31.7 | 33.9 | 39.4 | 43.2 | 45.3 | 0.89 | 0.75 |
| early-builder | 30.7 | 31.9 | 35.3 | 38.8 | 43.9 | 45.4 | 0.87 | 0.71 |
| baron-prestige | 31.4 | 31.3 | 34.4 | 39.9 | 45.3 | 47.6 | 0.82 | 0.89 |
| diversifier | 33.1 | 35.0 | 38.7 | 40.8 | 41.6 | 45.7 | 0.93 | 0.74 |
| builder | 33.3 | 33.9 | 36.1 | 41.9 | 44.1 | 45.7 | 0.78 | 0.63 |
| baron-tycoon | 33.6 | 35.1 | 38.8 | 42.7 | 48.2 | 50.9 | 0.73 | 0.67 |
| prestige | 35.6 | 38.0 | 40.3 | 44.3 | 45.8 | 46.2 | 0.66 | 0.82 |
| spoiler | 35.7 | 35.1 | 37.8 | 43.5 | 43.9 | 45.8 | 0.69 | 0.37 |
| straight | 36.4 | 41.3 | 41.4 | 42.6 | 45.6 | 48.7 | 0.74 | 0.21 |
| tycoon | 36.6 | 39.7 | 42.8 | 46.1 | 49.0 | 48.9 | 0.52 | 0.45 |
| churner | 39.3 | 41.4 | 44.3 | 45.7 | 47.4 | 52.5 | 0.34 | 0.00 |
| hoarder | 45.7 | 44.0 | 42.6 | 44.1 | 44.9 | 45.0 | 0.20 | 0.37 |

The largest standard error of a cell is 2.2 points. Every strategy but hoarder reaches the target
below noise 1.0, so none is capped. Hoarder already gives the reference player 45.7% at noise 0
and noise barely moves it (42-46% at every level); the script takes the least noise within a
point of the target, 0.2.

**Check on fresh maps** (`spec-easy-check.json`, maps 101-130, 90 games per strategy at the new
noise): the reference player takes 40.8% (builder) to 44.9% (churner), 43.1% overall (standard
error of one strategy about 1.0 point). The 2026-10-26 calibration gave 42.0% overall on the same
maps under the fleet rules.

**What changed.**

- **Most strategies need more noise.** Eight of the thirteen now play Easy at noise 0.7-0.93
  (fleet rules: five). At noise 1.0 the reference player takes 45-53%.
- **The pay-when-short strategies got harder.** straight (noise 0.21 to 0.74), churner (0.00 to
  0.34) and spoiler (0.37 to 0.69) need far more noise than under the fleet rules. Hoarder is the
  exception: it withholds so much that it is easier than the target without any noise.
- **The curves are noisier at low noise** (baron-prestige is flat at 31-32% from 0.0 to 0.3,
  diversifier dips at 0.9), within the cells' standard errors.

The caveat of the first calibration still applies: at Easy the strongest strategies play with
noise near 0.8-0.9, so the revealed strategy describes the plan the bot was following, not how
well it followed it.
