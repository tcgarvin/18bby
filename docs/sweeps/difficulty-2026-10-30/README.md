# Opponent difficulties under supply chains (2026-10-30)

Supply chains became the default rules, so both web difficulties were refitted with the method of
`difficulty-2026-10-28` and `-10-29`: the reference player (`builder@site`) seated with two bots
of one strategy, all three seat orders; targets 43% (`very-easy`) and 40% (`easy`).

**Fit.** `spec-easy.json` (13 strategies, noise 0.0-1.0 in steps of 0.1, maps 1-20, 8,580
games), fitted with

    uv run python docs/sweeps/difficulty-2026-10-25/calibrate.py rows.jsonl 0.43 builder@site
    uv run python docs/sweeps/difficulty-2026-10-25/calibrate.py rows.jsonl 0.40 builder@site

(`calibrate-0.43.txt`, `calibrate-0.40.txt`; the fitted values are in `fits.json`).

**Check on fresh maps** (`spec-check-<level>.json`, maps 101-130, 90 games per strategy;
`check-<level>.txt` from `docs/sweeps/difficulty-2026-10-29/check.py`): overall 42.4% for very
easy and 40.4% for easy, every strategy within about 2 points of its target except:

- **churner** is harder than the target at both levels (37.4% and 36.7%) and barely moves with
  noise; it keeps its earlier values (0.28 and 0.12) rather than the fitted 0.08 and 0.0.
- **hoarder** is easier (44.7% and 44.1%), as before: noise does not make it much harder.

Adopted in `BOT_NOISE` (`src/bby18/config.py`).
