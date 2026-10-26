# Easy opponents: noise calibration (2026-10-25)

The web app's named opponents (`src/bby18/bots/roster.py`) each play one stable strategy with a
`noise` (carelessness) level per difficulty. Noise makes a share-round decision a random pass or
buy, makes a build one of the next three by score, and flips a dividend decision at half the
rate. It never touches starting a corporation or buying toward floating one's own: those are the
plan, not its execution. Noise 0 plays exactly as the pure strategy.

**Target.** A reference player (the stable's `builder`) seated with two bots of one strategy
should take `DIFFICULTY_TARGET_SHARE` of the table's worth: 43% for Easy (fair is 33.3%; the
original web bot gives about 40%). At noise 1.0 every strategy gives about 45%.

**Calibration** (`spec-easy.json`, 8,580 games: 13 strategies x 11 noise levels x 3 seat orders x
20 maps; `calibrate.py rows.jsonl 0.43`). Reference share by opponent noise:

| strategy | 0.0 | 0.3 | 0.5 | 0.7 | 0.9 | 1.0 | Easy noise |
|---|---|---|---|---|---|---|---|
| baron | 27.7 | 32.0 | 35.0 | 38.2 | 41.5 | 44.8 | 0.95 |
| targeted | 29.2 | 34.1 | 37.2 | 39.7 | 43.3 | 45.1 | 0.89 |
| baron-prestige | 29.4 | 32.9 | 35.3 | 40.2 | 42.9 | 46.5 | 0.90 |
| early-builder | 30.7 | 34.9 | 36.9 | 40.3 | 43.3 | 43.9 | 0.89 |
| diversifier | 33.2 | 37.2 | 38.2 | 41.8 | 43.2 | 45.1 | 0.87 |
| baron-tycoon | 33.3 | 36.5 | 37.9 | 40.7 | 43.8 | 45.4 | 0.86 |
| builder | 33.3 | 37.3 | 40.5 | 42.0 | 43.4 | 45.1 | 0.86 |
| prestige | 34.7 | 37.4 | 39.7 | 42.7 | 44.7 | 47.7 | 0.72 |
| spoiler | 36.4 | 40.3 | 41.7 | 44.0 | 43.5 | 45.1 | 0.63 |
| hoarder | 37.1 | 40.0 | 42.6 | 43.0 | 43.4 | 44.8 | 0.69 |
| tycoon | 37.8 | 40.4 | 42.9 | 44.5 | 45.2 | 45.2 | 0.51 |
| churner | 38.4 | 41.0 | 43.3 | 44.9 | 46.6 | 46.9 | 0.40 |
| straight | 40.1 | 43.1 | 45.3 | 46.4 | 47.0 | 46.8 | 0.29 |

The largest standard error of a cell is 1.4 points, so the flatter curves (hoarder, spoiler) pin
their noise only loosely.

**Check on fresh maps** (`spec-easy-check.json`, maps 101-130, 90 games per strategy): the
reference player takes 41.7% (early-builder, tycoon) to 44.1% (straight), 42.6% overall.

**History.** The first calibration aimed at 45% and gave 45.2% on fresh maps, but playtesting
showed its bots rarely ran a company: a careless decision could be neither a start nor a float
buy, so at noise 0.9 a bot started its corporation on only one share-round turn in ten, and 35-45%
of the strongest strategies' bots never ran one. Noise now spares those buys, and `diversifier`
(which discounts its own shares and stranded half its starts even at noise 0) now floats what it
starts before buying elsewhere. The target moved to 43% to make Easy a little harder.

**Caveat.** The strongest strategies need noise near 0.9 to be Easy, so at Easy they play much
alike; the revealed strategy describes the plan the bot was following, not how well it followed
it.
