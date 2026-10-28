# Six corporations, 2026-10-27

**Question:** Death Star sites land at the bottom of the board almost every game. Do two more
corporations, at Mygeeto (IGB, InterGalactic Banking Clan) and Ryloth (RRC, Ryloth Ryll
Combine), spread the sites, and how do they change balance? Sites are still placed at setup from
every homeworld, floated or not: players should weigh where the Death Star is when choosing what
to float (user ruling).

**Setup:** 3 players, maps 1-20, 9 strategies (admiral, early-builder, targeted, baron,
contractor, baron-prestige, staller, builder, baron-tycoon), every lineup in every seat order:
14,580 games per variant. `spec-baseline.json` plays the deployed rules with today's bots;
`spec-site.json` plays every variant with `@site` bots (`start_order="site"`: home potential
plus the active site's contract value, full within 3 hexes of the homeworld and gone at 6,
times `contract_weight`). Without that, most archetypes start corporations in config order and
the two new ones would never float.

| Variant | Bots | Viable (equilibrium) | Best responses (of 45) | Launch | Contract share of revenue |
|---|---|---|---|---|---|
| four-plain (deployed) | plain | staller 61%, baron 39% | admiral 14, baron 11, targeted 8, staller 7, contractor 5 | 26% | 10.7% |
| four | @site | baron 100% | contractor 19, baron 16, targeted 10 | 29% | 12.5% |
| six-d4 | @site | baron *or* admiral alone | admiral 27, targeted 11, baron 6, contractor 1 | 19% | 12.7% |
| six-d5 | @site | targeted 66%, staller 34% | targeted 22, staller 13, baron 5, admiral 5 | 11% | 8.0% |
| six-d5-c14 | @site | identical to six-d5 | | | |

`d5` is `death_star_max_homeworld_distance=5`; `c14` is `certificate_limit=14`.

**Floats** (`floats.txt`; share of games each corporation floats):

| Variant | CEC | KDY | CSC | KTG | IGB | RRC |
|---|---|---|---|---|---|---|
| four-plain | 100% | 100% | 91% | 27% | | |
| four | 100% | 100% | 21% | 99% | | |
| six-d4 | 57% | 100% | 0% | 100% | 1% | 57% |
| six-d5 | 64% | 100% | 0% | 100% | 10% | 44% |

**Findings:**

- Site-aware starting alone (four vs four-plain) narrows balance to one viable strategy. Human
  players will look at the site, so the deployed game may be less balanced than the plain-bot
  tournament says.
- Six corporations with distance 5 restore two viable strategies and spread best responses, but
  they do it partly by weakening the station: launches fall to 11%, contracts to 8% of revenue,
  and contractor drops to last. Distance 4 keeps the station but lets admiral dominate.
- The certificate limit does not bind: bots start about 3.2 corporations a game, and 12 versus 14
  plays identically.
- Coruscant (CSC) never floats with site-aware bots once there are six corporations, and Mygeeto
  (IGB) rarely does: both are far from every site. KDY and KTG always float.
- Only 20 seeds, so 20 site layouts per variant.

The specs name the corporations and `"planet_pair_bonus": {}` explicitly, so they still play
these rules now that six corporations and the bonus are the default.

Files: `report-*.txt` (`bby18 tournament-report` per variant), `dsreport.txt`
(`bby18 death-star-report`, every variant), `floats.txt` (scratch script, not kept).

## Adopted rules (2026-10-28)

The user chose six corporations at distance 4, with Coruscant's pairs worth +10
(`planet_pair_bonus`) and the Death Star numbers unchanged. `spec-adopted.json` (variant `{}`,
`@site` bots; `report-adopted.txt`, `dsreport-adopted.txt`, `floats-adopted.txt`):

- **Balance** as in six-d4: one equilibrium (baron alone); best responses admiral 27, targeted 9,
  baron 8, contractor 1 of 45; bootstrap viable count mean 1.5 (1-3).
- **Station:** launches 18%, contracts 12.5% of revenue, bankruptcies under 1 game in 100.
- **Floats:** KDY and KTG 100%, CEC 57%, RRC 50%, CSC 7% (0% without the bonus), IGB 1%.
  The bonus barely moves Coruscant; IGB at Mygeeto is still almost never started.
