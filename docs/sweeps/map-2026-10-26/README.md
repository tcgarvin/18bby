# The east edge cut, and Kashyyyk (2026-10-26)

The designer found Kashyyyk a hard pick ("the dead zone around Kashyyyk") and asked to try
removing every hex east of Ryloth. Fable consulted on the map; the bots measured it. Adopted: the
cut alone (`map-117.json`, see "East edge cut" in `docs/DECISIONS.md`). Not adopted: moving
planets to fix Kashyyyk, because it breaks the Death Star balance.

## The cut

Ten empty hexes go: those with `2q + r > 8`, strictly east of Ryloth's column. 117 hexes remain,
93 of them space; no planet moves, and Mon Cala, Lothal, Kessel and Ryloth become edge planets.
The Death Star sites barely move: none of the cut hexes was within 4 hexes of two homeworlds.

**Corporations** (`spec-corporations.json`, 4 players so all four float, 150 maps per lineup).
Final share price, CEC / KDY / CSC / KTG:

| Every seat plays | 127-hex | cut |
|---|---|---|
| builder | 92 / 100 / 72 / 67 | 96 / 100 / 77 / 74 |
| straight | 76 / 87 / 63 / 52 | 81 / 92 / 61 / 61 |
| baron | 185 / 182 / 158 / 148 | 181 / 180 / 154 / 147 |

**Strategy balance** (`spec-tournament.json`, 3 players, the 8 strategies that carry the
equilibrium in `docs/sweeps/death-star-2026-10-25`, every seat order, maps 1-20; 10,240 games
per variant). The 127-hex row reproduces the full 12-strategy result of 2026-10-26 exactly.

| | Equilibrium | Bootstrap viable (mean) | Largest on resamples |
|---|---|---|---|
| 127-hex | baron 75%, early-builder 9%, targeted 9%, admiral 7% | 2.9 | baron 56%, early-builder 28% |
| cut | early-builder 54%, admiral 25%, baron 21% | 2.3 | early-builder 58%, baron 36% |

The station launched in 37% of the cut games.

## Why Kashyyyk is hard

Kashyyyk is R and pairs only with I or S, all three or more hexes away: its first pair takes two
tiles (about 160 on a seeded sky) where Corellia's and Kuat's take one (about 65). It catches up
by the middle game but has paid for it in share price. Coruscant has the same slow opening and
also sits about 8 hexes from both Death Star sites (about one contract a game), because the
first site lands at (-5,6), next to Bespin, on 64% of maps: the only Outer Rim hex within 4 hexes
of two homeworlds.

## Candidates not adopted

All on the cut map; 4-player builder final prices CEC / KDY / CSC / KTG.

| Change | Result |
|---|---|
| Druckenwell to (0,2) | Looked best on the map alone (Kashyyyk's first pair about 69), but every corporation earned about 15% less: Druckenwell also fed Kuat and Malastare. 84 / 84 / 67 / 60 |
| Alderaan M to A | Does nothing for Coruscant (Alderaan is 3 hexes away) and weakens Corellia |
| Kashyyyk to (-1,1) | 88 / 92 / 68 / 92 |
| **F:** Kashyyyk to (-1,0) | 86 / 94 / 67 / 93. Kuat and Kashyyyk become a one-tile S-R pair |
| **FE:** F, and Chandrila to (-4,-1) | 87 / 92 / 85 / 90. Chandrila (A) sits one tile from three M worlds |
| FE, and Bimmisaari to (2,-1) | No help to the east: Kessel and Lothal reached less often |

Every moved planet keeps its region's shading. But in the 3-player tournament F gives baron 100%
of the equilibrium and FE makes admiral dominant (best response to 27 of 36 opponent sets,
largest on every resample). Moving Kashyyyk moves the Death Star sites (the first site now lands
at (-1,-5) on about a sixth of maps), so the station launches half as often (22%) and the clock no
longer checks the always-pay and fleet strategies. FE also makes the east later-game territory
(Bothawui reached in 39% of 4-player games instead of 52%). Mon Cala is reached in 2-4% of games
on every map.

Next step if Kashyyyk is revisited: FE together with a faster Death Star clock or a site rule
that spreads the sites (toward Coruscant).

## Easy opponents recalibrated

The method of `docs/sweeps/difficulty-2026-10-25`, unchanged (`spec-easy.json`, 8,580 games;
`uv run python docs/sweeps/difficulty-2026-10-25/calibrate.py rows.jsonl 0.43`). Noise for 43%:

| strategy | 127-hex | cut |
|---|---|---|
| baron | 0.81 | 0.75 |
| baron-prestige | 0.88 | 0.89 |
| baron-tycoon | 0.62 | 0.67 |
| builder | 0.65 | 0.63 |
| churner | 0.03 | 0.00 |
| diversifier | 0.71 | 0.74 |
| early-builder | 0.83 | 0.71 |
| hoarder | 0.33 | 0.37 |
| prestige | 0.80 | 0.82 |
| spoiler | 0.39 | 0.37 |
| straight | 0.20 | 0.21 |
| targeted | 0.74 | 0.68 |
| tycoon | 0.52 | 0.45 |

Largest standard error of a cell: 2.1 points. **Check on fresh maps** (`spec-easy-check.json`,
maps 101-130, 90 games per strategy): the reference player takes 39.1% (early-builder) to 43.6%
(baron-tycoon), 42.0% overall (42.2% for the previous calibration on the 127-hex map).
