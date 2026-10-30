# Supply chains, 2026-10-30

**Question:** corporations grew to about two routes and stopped, and Outer Rim to Core routes
never paid. Do supply chains (routes that climb raw goods → Industry → Market/Shipyard → Death
Star, stopping in the middle at the corporation's own facilities, one chain per facility, the
owner choosing what a seizure takes) make routes worth extending, without breaking balance? And
does the facility limit need to rise from 3 to 4? See "Supply chains" in `docs/DECISIONS.md`.

**Setup:** `spec-tournament.json`: 3 players, maps 1-20, the 9 `@site` strategies of the
six-corporations sweep, every lineup in every seat order: 14,580 games per variant. `facilities`
is the rules of 2026-10-28 (`FACILITY_CONFIG`); `chains-l3` and `chains-l4` turn `chain_rules`
on with limit 3 and 4. The bots value a facility as a middle stop and surrender the facility
whose loss costs the least revenue. (The spec names the variants by override, so after adoption
`facilities` would need `"chain_rules": false` to replay.)

| Variant | Viable (equilibrium) | Best responses (of 45) | Bootstrap viable | Launch | Contracts |
|---|---|---|---|---|---|
| facilities | baron 100% | admiral 27, targeted 9, baron 8, contractor 1 | 1.5 (1-3) | 18% | 12.5% |
| chains-l3 | targeted 80%, baron 20% | targeted 30, baron 7, admiral 6, early-builder 1, baron-tycoon 1 | 1.6 (1-3) | 25% | 11.6% |
| chains-l4 | baron 100% | targeted 19, baron 19, admiral 5, early-builder 1, baron-tycoon 1 | 1.5 (1-3) | 25% | 11.4% |

**Chains** (`dsreport-tournament.txt`, chains-l3; l4 within a point):

- 1.74 chains per operating turn; 59% two stops, 39% three, 1.4% four (Resources → Industry →
  Shipyard → Death Star).
- 63% of all revenue comes from chains with a middle stop; regional bonuses are 6.5% of revenue,
  earned by 15% of chains.
- 4.9 surrenders per game; 8% of them break a running chain, costing about 21 a turn each.

**Other effects:** network actions per corporation 7.65 → 8.10, late (round 5 on) 0.86 → 0.96;
planets touched per game 12.7 → 13.4; stage 2 fills in 84% of games (74%), the station launches
in 25% (18%); bankruptcies stay under 1 in 100 games, though limit 4 doubles contractor's.

**Findings:**

- Chains do what they were meant to: most revenue now runs through middle stops, and building
  continues a little later, though late building is still thin.
- Balance is no worse: at limit 3 two strategies coexist (targeted and baron), where the current
  rules have baron alone; the bootstrap count barely moves.
- The limit of 4 does not bind for these bots (corporations end with 1.7-1.8 facilities either
  way) and narrows the equilibrium back to baron alone. Humans who buy spare facilities to protect
  a chain may hit 3 more often than bots do.

**Adopted:** chains with limit 3 (`chains-l3`), as the default rules.

Files: `report-<variant>.txt` (`bby18 tournament-report --variant`), `dsreport-tournament.txt`
(`bby18 death-star-report`, all variants). Rows were not kept (43,740 games, about 90 minutes
on 14 workers).
