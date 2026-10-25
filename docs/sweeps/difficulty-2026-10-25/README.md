# Easy opponents: noise calibration (2026-10-25)

The web app's named opponents (`src/bby18/bots/roster.py`) each play one stable strategy with a
`noise` (carelessness) level per difficulty. Noise makes a share-round decision a random pass or
buy, makes a build one of the next three by score, and flips a dividend decision at half the
rate. Noise 0 plays exactly as the pure strategy.

**Target.** A reference player (the stable's `builder`) seated with two bots of one strategy
should take `DIFFICULTY_TARGET_SHARE` of the table's worth: 45% for Easy (fair is 33.3%; the
original web bot gives about 40%). 50% was the first choice but is out of reach: at noise 1.0
every strategy plays alike and gives about 49.7%.

**Calibration** (`spec-easy.json`, 8,580 games: 13 strategies x 11 noise levels x 3 seat orders x
20 maps; `calibrate.py rows.jsonl 0.45`). Reference share by opponent noise:

| strategy | 0.0 | 0.3 | 0.5 | 0.7 | 0.9 | 1.0 | Easy noise |
|---|---|---|---|---|---|---|---|
| baron | 27.7 | 32.9 | 36.3 | 39.8 | 44.2 | 49.7 | 0.91 |
| targeted | 29.2 | 35.1 | 38.8 | 41.5 | 44.7 | 49.7 | 0.91 |
| baron-prestige | 29.4 | 37.4 | 41.9 | 44.7 | 46.1 | 49.7 | 0.71 |
| early-builder | 30.7 | 35.1 | 37.5 | 41.3 | 43.7 | 49.7 | 0.92 |
| baron-tycoon | 33.3 | 37.1 | 39.7 | 41.2 | 45.0 | 49.7 | 0.90 |
| builder | 33.3 | 37.9 | 40.7 | 41.8 | 45.2 | 49.7 | 0.88 |
| prestige | 34.7 | 41.4 | 43.9 | 46.6 | 47.1 | 49.7 | 0.54 |
| spoiler | 36.4 | 40.3 | 43.2 | 44.1 | 45.1 | 49.7 | 0.89 |
| hoarder | 37.1 | 40.9 | 42.7 | 44.5 | 44.6 | 49.7 | 0.91 |
| tycoon | 37.8 | 43.0 | 44.0 | 44.4 | 45.7 | 49.7 | 0.75 |
| churner | 38.4 | 40.9 | 43.0 | 46.2 | 45.9 | 49.7 | 0.56 |
| straight | 40.1 | 42.8 | 45.5 | 46.6 | 45.9 | 49.7 | 0.47 |
| diversifier | 50.1 | 45.1 | 45.5 | 45.2 | 44.9 | 49.7 | 0.30 |

Diversifier is the one strategy noise makes harder (a careless buy is sometimes its own company),
so it gets the least noise that lands near the target.

**Check on fresh maps** (`spec-easy-check.json`, maps 101-130, 90 games per strategy): the
reference player takes 44.2% (baron) to 46.6% (diversifier), 45.2% overall.

**Caveat.** The strongest strategies need noise near 0.9 to be Easy, so at Easy they play much
alike; the revealed strategy describes the plan the bot was following, not how well it followed
it.
