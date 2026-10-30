# Easy opponents, and the old easy renamed very easy (2026-10-29)

The level calibrated on 2026-10-28 (target 43%) is renamed `very-easy`, unchanged. The new `easy`
targets 40%: the reference player (`builder@site`) should take 40% of the worth when seated with
two bots of one strategy, against a fair 33.3%. Same rules, roster and method as
`difficulty-2026-10-28`.

**Fit.** The `difficulty-2026-10-28` rows (`spec-easy.json` there: 13 strategies, noise 0.0-1.0
in steps of 0.1, maps 1-20) refitted for 0.40 put most strategies near target, but a check on
fresh maps had churner at 34.7% and hoarder at 46.8%, both fitted on bumpy 20-map curves.
`spec-easy-refit.json` adds maps 21-60 at the five noise levels around each strategy's first fit
(7,800 games); the fit below (`calibrate.txt`) is on those rows plus the 2026-10-28 rows, so the
cells near each fit average 60 maps and the rest 20.

    cat <refit rows> <2026-10-28 spec-easy rows> > rows.jsonl
    uv run python docs/sweeps/difficulty-2026-10-25/calibrate.py rows.jsonl 0.40 builder@site

| strategy | 0.0 | 0.3 | 0.5 | 0.7 | 0.9 | 1.0 | Easy noise | Very easy noise |
|---|---|---|---|---|---|---|---|---|
| baron | 29.3 | 31.5 | 33.0 | 38.1 | 43.2 | 47.0 | 0.79 | 0.91 |
| early-builder | 29.3 | 30.9 | 32.9 | 38.3 | 43.4 | 47.1 | 0.76 | 0.89 |
| targeted | 29.6 | 31.5 | 33.7 | 39.8 | 45.4 | 47.0 | 0.71 | 0.86 |
| baron-tycoon | 29.9 | 32.0 | 33.0 | 38.4 | 43.7 | 47.5 | 0.77 | 0.90 |
| baron-prestige | 30.7 | 31.2 | 32.2 | 38.1 | 42.8 | 46.7 | 0.85 | 0.92 |
| diversifier | 33.1 | 35.5 | 39.2 | 41.4 | 44.5 | 45.5 | 0.56 | 0.88 |
| tycoon | 33.3 | 35.2 | 38.8 | 41.3 | 44.6 | 45.8 | 0.56 | 0.85 |
| builder | 33.3 | 35.3 | 38.6 | 41.0 | 44.5 | 45.5 | 0.56 | 0.86 |
| prestige | 33.6 | 35.8 | 39.0 | 40.5 | 44.8 | 49.7 | 0.60 | 0.86 |
| spoiler | 35.7 | 37.4 | 39.8 | 42.7 | 43.6 | 45.5 | 0.51 | 0.74 |
| straight | 37.4 | 41.6 | 41.9 | 42.3 | 45.9 | 48.5 | 0.11 | 0.74 |
| churner | 38.3 | 41.7 | 46.4 | 47.4 | 47.5 | 48.4 | 0.12 | 0.28 |
| hoarder | 56.9 | 49.4 | 43.7 | 42.5 | 44.3 | 46.6 | 0.70 | 0.60 |

**Hoarder is the one character easier than the target.** It is much easier at no noise (57%:
it hoards cash the reference player outbuilds) and noise makes it harder only down to about
42.5% at 0.7-0.8. Straight and churner have little room too: they reach 40% at about 0.1 noise.
Easy cannot go much below 40% with every character on target; a harder level needs stronger
play from hoarder (and soon churner and straight), not less noise.

**Check on fresh maps** (`spec-easy-check.json`, maps 101-130, 90 games per strategy;
`uv run python docs/sweeps/difficulty-2026-10-29/check.py rows.jsonl`):

| strategy | share | s.e. |
|---|---|---|
| churner | 38.9 | 1.1 |
| spoiler | 39.4 | 1.3 |
| diversifier | 39.5 | 1.1 |
| prestige | 39.7 | 1.3 |
| early-builder | 39.8 | 1.2 |
| baron-tycoon | 39.9 | 1.3 |
| targeted | 40.1 | 1.2 |
| straight | 40.2 | 1.1 |
| builder | 40.2 | 1.2 |
| baron-prestige | 40.6 | 1.4 |
| baron | 40.7 | 1.3 |
| tycoon | 40.7 | 1.2 |
| hoarder | 43.5 | 1.2 |
| overall | 40.2 | |

Very easy's check on the same maps (`difficulty-2026-10-28`) was 43.0% overall, so the two levels
are about 3 points apart.
