# Death Star and fleets: does it end the dominant strategy? (2026-10-25/26)

Question: the 2026-10-25 stable tournament found that paying every dividend (`baron`) dominated,
because nothing ever declined. Do the Death Star and fleet rules (`docs/DECISIONS.md`, "Death
Star and fleets") leave no single dominant strategy, and do they make withholding, selling and
timing matter?

**Answer: yes, after one placement change.** With the sites placed where at least two homeworlds
can contest them and five cubes per stage (`near4_short`), four distinct strategies coexist when
pooled over 20 maps, the best strategy varies from map to map, and players sell three times as
often in the stock round before a seizure or site move. Under the old rules on the same maps,
always-pay wins everywhere. As first designed, the rules changed little: the station launched in
3% of games and contracts were 6% of revenue.

## Method

- Stable tournament as in `docs/sweeps/stable-2026-10-25/`: every 3-player table of 12 strategies
  in every seat order, worth share as payoff, replicator dynamics and seed bootstrap
  (`bby18 tournament-report`). Death Star measurements from `bby18 death-star-report`.
- Twelve strategies (`bots/stable.py`): the earlier baron, targeted, early-builder, investor,
  baron-tycoon, baron-prestige and builder, plus five written for these rules:
  - **admiral**: buys four cheap fleets early, pushing rivals onto dearer tiers.
  - **contractor**: rushes the construction site and pays everything.
  - **staller**: never builds toward the site and withholds for builds.
  - **saver**: always pays but keeps two fleets' price in the treasury.
  - **raider**: one fleet; sells its own shares before a seizure.
- Every bot was first taught the rules: a re-fleet reserve before a likely seizure, fleets
  valued by the revenue they add, build scores under the pair cap, and site value discounted by
  how long the site will last. In 160 smoke games, no bot went bankrupt by accident.
- **Caution:** with the rules off, admiral, contractor, raider and saver play exactly like baron,
  and staller like targeted. In the rules-off reports they are clones, and their "viability"
  there is baron's. Found afterwards: with the rules on, `builder` and `targeted` (and `hoarder`)
  also played identical games, because the bots' Death Star dividend logic overrode the knobs
  that told them apart. Treat their rows as one strategy. (Fixed 2026-10-26, together with a
  wider seizure margin for the re-fleet reserve, which changes every bot's play; these results
  predate both. See `docs/sweeps/difficulty-2026-10-26`.)
- Every spec spells out its Death Star numbers. They were written when the default was the old
  rules (6 cubes per stage, sites anywhere); the adopted default differs.

| Spec | What | Games |
|---|---|---|
| `spec.json` | old rules vs. Death Star rules as designed, seeds 1-10 | 34,560 |
| `spec-explore1.json`, `spec-explore2.json` | six fixed lineups x 24 maps per tuning variant | 1,008 + 1,152 |
| `spec-candidates.json` | three tuned candidates, seeds 1-10 | 51,840 |
| `spec-confirm.json` | `near4_short` on fresh seeds 11-20 | 17,280 |
| `spec-base-confirm.json` | old rules on seeds 11-20, for comparison | 17,280 |

`seats.py rows.jsonl VARIANT` prints seat shares and each map's top strategies.

## As designed: the Death Star barely mattered

`report-ds.txt`, `dsreport-base.txt`:
- The station launched in **3%** of games; 97% ended at the round-8 backstop.
- Contracts were **6%** of revenue; the Empire's automatic cubes outnumbered deliveries 8 to 4.
- Always-pay still won: it was the best response to 30 of 78 opponent pairs (admiral 28), and
  replicator dynamics settled on baron 90%.

The cause was distance. The first site sat 7-9 hexes from the Core homeworlds, so reaching it
cost most of a corporation's capital for a 40-50 contract that lasted only until the site moved.

## Tuning (`dsreport-explore1.txt`, `dsreport-explore2.txt`)

| Variant | Launches | Contract share of revenue |
|---|---|---|
| as designed | 6% | 7% |
| Empire 2 cubes per stock round | 15% | 6% |
| contracts 60/70/80/90 ("rich") | 13% | 13% |
| rich + 4 cubes/stage + Empire 2 | 100% | 6% |
| **sites within 4 of 2 homeworlds ("near4")** | **37%** | **18%** |
| near4 + 5 cubes/stage (**near4_short**) | 51% | 16% |
| near4 + rich | 43% | 25% |

Faster Empire cubes alone make the station a timer that ignores the players. Contested
placement is what makes contracts worth chasing.

## Candidates (`report-near4_*.txt`)

| Variant | Equilibrium | Bootstrap viable (mean/min) | Largest basin |
|---|---|---|---|
| near4_rich | contractor 96% | 1.6 / 1 | contractor 100% |
| near4_rich_short | contractor 90%, admiral 10% | 1.9 / 1 | contractor 95% |
| **near4_short** | baron 41%, admiral 34%, contractor 17%, early-builder 8% | 2.9 / 2 | rotates |

Richer contracts tip the game to contractor. `near4_short` sits just below that cliff, so contract
values are the most sensitive number in the set.

## Confirmation on fresh maps

- **Seeds 11-20 alone** (`report-near4_short-confirm.txt`): staller 92%, with bootstrap viable
  2.6 on average (min 1) and staller largest in 65% of resamples. On these maps, the strategy
  that withholds and ignores the site wins.
- **Pooled, seeds 1-20** (`report-near4_short-20seeds.txt`, `dsreport-near4_short-20seeds.txt`):
  - Equilibrium baron 47%, admiral 25%, early-builder 16%, contractor 11%.
  - Bootstrap viable 3.2 on average (min 2, max 5); the largest basin is early-builder 40%,
    baron 30%, admiral 13%, staller 10%.
- **Old rules on seeds 11-20** (`report-base-confirm.txt`): always-pay is the largest basin in
  **100%** of resamples, as on seeds 1-10.
- **Best strategy on each map** (by mean share): admiral leads on 11 of 20 maps; early-builder,
  contractor, staller and raider lead on the rest.

**Reading.** Under the old rules one plan wins on every map. Under `near4_short` the best plan
depends on the map: sometimes grab fleets early, sometimes rush the site, sometimes stay away from
it and withhold. Within one map the advantages are small (top shares 35-38%). Most strategies near
the top still pay out, but on some maps a withholding strategy wins, which the old rules never
allowed.

## Does play change? (`near4_short`, 20 seeds)

| Measure | Old rules | near4_short |
|---|---|---|
| Station launched | — | 43% (backstop 57%) |
| Stage fills (clock, OR r.i = 2(r-1)+i) | — | 4.7 / 7.1 / 10.6 / 12.9 |
| Contract revenue | — | 14% of revenue; 8.4 of 15.9 cubes |
| Shares sold per stock round | 0.05 | 0.33; **0.56 before a seizure or move** vs 0.19 otherwise |
| Withheld dividends | 14% of turns | 22%; 23.5% near a seizure vs 20.5% otherwise |
| Bankruptcies | — | 2% of games, mostly presidents of two companies (baron-tycoon) |
| Fleets per corporation | — | bought 3.4, seized 1.4, 2.0 at the end |
| Seat shares (1/2/3) | 32.8 / 35.4 / 31.8 | 34.4 / 36.2 / 29.4 |

## Open points for the designer

- **Most games still end on the clock** (57%), and a launch lands only about a round before the
  backstop. If the Battle of Yavin should be the usual ending, try 4 cubes per stage (Fable's
  suggestion); expect more early bankruptcies.
- **Contract values are a cliff:** +20 per stage hands the game to contractor.
- **Seat 3 is weaker** than before (29.4% share, 15.5% wins); the skew predates these rules.
- **Investor and saver are weak:** non-presidents bear seizure risk without control, and a second
  reserve fleet is wasted money because one is always enough.
- **Placement:** contested placement pulls the Outer Rim site toward the homeworlds (often near
  Bespin or Sullust). Theme vs play is the designer's call.
- **Placeholders** chosen while building are listed in DECISIONS.md: the reserved future site,
  and a bankrupt company's president being free to start another.

Fable (design consultant) reviewed the candidates. It agreed `near4_short` is a real improvement,
and noted that the variety is mostly in fleet timing and site strategy rather than pay vs.
withhold, and that coexistence is partly "a different winner per map".
