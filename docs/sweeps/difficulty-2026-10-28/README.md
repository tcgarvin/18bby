# Easy opponents: noise recalibrated for six corporations (2026-10-28)

Six corporations, Coruscant's +10 pair bonus (see "Six corporations" in `docs/DECISIONS.md`) and
site-aware starting for the web opponents (`roster_policy`: every roster strategy but churner,
which starts at random, plays `start_order="site"`). The method of
`docs/sweeps/difficulty-2026-10-25` is unchanged (target 43% for the reference player, 13 roster
strategies, 11 noise levels, 3 seat orders, maps 1-20), except that the reference player and the
opponents play the `@site` kinds: the specs are those of `difficulty-2026-10-27` with `@site`
added. `uv run python docs/sweeps/difficulty-2026-10-25/calibrate.py rows.jsonl 0.43 builder@site`.

| strategy | 0.0 | 0.3 | 0.5 | 0.7 | 0.9 | 1.0 | Easy noise | 2026-10-27 |
|---|---|---|---|---|---|---|---|---|
| baron | 29.3 | 31.5 | 33.0 | 36.8 | 42.5 | 46.2 | 0.91 | 0.89 |
| early-builder | 29.3 | 30.9 | 32.9 | 37.8 | 43.2 | 45.9 | 0.89 | 0.87 |
| targeted | 29.6 | 31.5 | 33.7 | 38.2 | 43.8 | 46.0 | 0.86 | 0.86 |
| baron-tycoon | 29.9 | 32.0 | 33.0 | 37.3 | 42.9 | 46.3 | 0.90 | 0.73 |
| baron-prestige | 30.7 | 31.2 | 32.2 | 37.9 | 41.7 | 47.7 | 0.92 | 0.82 |
| diversifier | 33.1 | 35.5 | 36.2 | 40.3 | 43.4 | 45.5 | 0.88 | 0.93 |
| tycoon | 33.3 | 35.2 | 37.4 | 39.9 | 43.7 | 45.8 | 0.85 | 0.52 |
| builder | 33.3 | 35.3 | 37.6 | 40.0 | 43.1 | 45.5 | 0.86 | 0.78 |
| prestige | 33.6 | 35.8 | 36.7 | 40.5 | 45.3 | 49.7 | 0.86 | 0.66 |
| spoiler | 35.7 | 37.4 | 39.1 | 42.5 | 43.6 | 45.5 | 0.74 | 0.69 |
| straight | 37.4 | 40.0 | 38.9 | 42.3 | 45.9 | 48.5 | 0.74 | 0.74 |
| churner | 39.7 | 43.1 | 46.4 | 47.4 | 47.5 | 48.4 | 0.28 | 0.34 |
| hoarder | 56.9 | 47.1 | 40.8 | 41.8 | 44.3 | 46.6 | 0.60 | 0.20 |

The largest standard error of a cell is 2.6 points. Hoarder is far easier than the target at
noise 0 (57%) and noise makes it harder; the script takes the least noise within a point of the
target, 0.6. The two-presidency strategies (tycoon, baron-tycoon) and prestige need much more
noise than before: with six corporations they find a second good start.

**Check on fresh maps** (`spec-easy-check.json`, maps 101-130, 90 games per strategy at the new
noise): the reference player takes 40.9% (spoiler) to 45.2% (straight), 43.0% overall (standard
error of one strategy about 1.2 points).
