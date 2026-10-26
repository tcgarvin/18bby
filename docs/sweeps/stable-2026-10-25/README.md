# Strategy stable tournament (2026-10-25)

> **Note (2026-10-26).** These specs were run when an empty variant (`{}`) meant the rules without
> the Death Star, which became the default on 2026-10-26. To rerun them under the rules they
> measured, add `"death_star_rules": false` to each variant (`CLASSIC_CONFIG` in `config.py`).

Question: under the current rules, does one strategy dominate? The balance goal is not that every
strategy is viable or wins equally, but that **no single strategy dominates**, with at least two
viable strategies and more being better.

## Method

- **Stable:** named `GreedyPolicy` archetypes in `src/bby18/bots/stable.py`. Each is a coherent
  plan (pay everything, withhold for builds, never start a corporation, start two cheap ones, dump
  the leader's shares, and so on). Every archetype except `straight` prices routes around terrain;
  `straight` is the bot the web app seats today. Each was checked to play differently from
  `builder` on 8 seeds. A "loyalist" (larger own-share bonus, up to 100x) played identically to
  `builder` and was dropped: the default bot already buys its own corporation whenever it can.
- **Tournament:** every multiset of three strategies, in every distinct seat order, on the same
  seeds (`"tournament": "stable"` in a sweep spec). Payoff is **worth share**: final worth over the
  table's total (fair = 33.3%).
- **Analysis** (`bby18 tournament-report --rows rows.jsonl`): mean share, invasion matrix (one
  row strategy against two copies of the column strategy), best response to each of the 105
  opponent pairs, and replicator dynamics on the full three-player payoff table. Strategies that
  keep at least 5% of the population at the end count as surviving. Seeds are bootstrapped.

| File | What |
|---|---|
| `spec-base.json` | current rules, all 14 strategies, 10 seeds: 27,440 games |
| `spec-variants.json` | four rule variants, 10 strategies, 6 seeds each |
| `exploit_search.py` | random search over bot knobs for a best response to a population |

## Baseline: current rules

| Strategy | Plan | Mean share | Win rate |
|---|---|---|---|
| baron | pay every dividend | **39.2%** | **76.6%** |
| targeted | withhold only when a revenue-gaining build is unaffordable | 38.0% | 66.7% |
| baron-prestige | pay everything, start at the highest par it can float alone | 37.6% | 61.9% |
| early-builder | withhold the first two rounds, then pay everything | 37.0% | 48.2% |
| baron-tycoon | pay everything, start two cheap corporations | 34.9% | 46.0% |
| builder | the original bot's rule: pay once treasury holds two builds | 34.4% | 35.0% |
| prestige | highest floatable par | 32.4% | 19.6% |
| spoiler | sell the richest rival's corporation | 32.0% | 31.6% |
| tycoon | two cheap corporations | 31.2% | 17.0% |
| investor | never start a corporation; buy the best yield; sell losers | 31.1% | 19.6% |
| hoarder | pay only with four builds in the treasury | 31.0% | 15.6% |
| churner | sell losers, random start | 30.5% | 14.9% |
| diversifier | discount its own corporation's shares | 29.0% | 4.0% |
| straight | web app bot (straight-line routing) | 28.5% | 9.9% |

(Mean share is against a uniformly random pair of opponents from the stable.)

**Baron dominates.** It is the best response to 83 of the 105 opponent pairs, and the remainder
go to its close relatives (early-builder 7, baron-prestige 6, baron-tycoon 5) plus investor (3)
and targeted (1). Against two copies of any other strategy it takes 35-50%. Replicator dynamics
settle on baron 82% and investor 18% from every start and in all 30 bootstrap runs. But
investor's foothold is a single cell: 34.4% against two barons, from 30 games, about one
standard error above a fair share. **The honest reading is one dominant strategy plus a free
rider that cannot be told apart from par.** That fails the balance goal.

Why paying wins: a payout moves the price right and pays the holders; a withhold moves it left.
Treasury is worth nothing at the end, the two-action cap limits what extra cash can buy, and by
mid-game most of the frontier is built. Withholding buys at most one extra build and costs
roughly two columns of price swing. 18xx games usually make withholding right through a forced
corporate expense (trains); 18BBY has none.

Other findings:

- **The web app's bot is weak.** `straight` is last at 28.5%. Path routing alone (`builder`)
  is worth about 6 points of share. The web opponents are currently the worst builders in the
  stable.
- **Seat order matters little in mixed tables.** Mean share by seat 33.2 / 34.3 / 32.5%, wins
  36.7 / 36.0 / 27.3%. (Identical bots in every seat show a much larger seat-1 edge; strategy
  differences swamp it.)
- **Investor collapses against early-builders (2.7%).** Partly a bot weakness: early-builders
  withhold for two rounds, their prices fall below par, and investor's sell-losers rule dumps
  its holdings at the bottom just before they start paying. A human investor would read the
  president's plan.
- **Diversifiers give worth away.** Almost any strategy takes about 50% against two
  diversifiers.

## Rule variants

Four variants from the design discussion, each a tournament of the ten dividend and starting
strategies (diversifier, churner, spoiler and straight dropped as weak or off-axis) over 6 seeds,
6,000 games each. The baseline row is the base run restricted to the same strategies and seeds.

| Variant | Overrides | Best responses (of 55) | Replicator survivors | Mean table worth |
|---|---|---|---|---|
| baseline | none | baron 43, others 12 | baron 81%, investor 19% (all bootstraps) | 9,892 |
| float4 | `float_capital_shares: 4` | early-builder 44, targeted 8 | one of targeted / early-builder | 5,271 |
| free_withhold | `withhold_moves_price: false` (new switch) | baron 31, investor 11, early-builder 9, targeted 3 | 2-3: targeted or baron, plus investor | 11,400 |
| treasury50 | `treasury_in_final_worth: 0.5` (new switch) | baron 42 | baron 81%, investor 19% | 10,119 |
| dearer | builds 90 / 90 / 120, nebula +45 | baron-prestige 32, baron 17 | baron 87%, investor 13% | 4,841 |

- **float4** does make capital bind, but it only swaps the dominant strategy: withholding early
  now beats everything, and worth halves.
- **treasury50** changes nothing measurable. End-game treasury value is not what decides it.
- **dearer** keeps paying on top and halves worth.
- **free_withhold** spreads the best responses, but mostly by blurring strategies together.
  With the left move gone, targeted is "baron who sometimes keeps a dividend to build"; the
  two are even against each other (33.8% and 32.8% invading each other's tables), and the
  replicator's choice between them is a coin flip (bootstrap 53/47). Baron still never falls
  below a fair share in any column. The telling cell is early-builder against two barons:
  28.3%, so withholding for two rounds still loses even when it costs nothing in price. The
  problem is not the penalty but the sink: hoarded cash has nothing worth buying. Free
  withholding also makes prices nearly monotone, so holding anyone's shares has no downside;
  investor (34-40% against every resident) is the one strategy it clearly strengthens, and
  table worth inflates.
- **Reading across the four:** scarcer capital is the one lever that moved dominance (float4
  flipped it). The next step is to interpolate it: `float_capital_shares: 6` and
  `capitalization: "incremental"`, which floats with 5x par and grows as later IPO shares sell.

Both new switches are `EXPERIMENTAL` fields in `config.py` that default to the current rules.
None of these is an adopted rule.

## Exploit search

`exploit_search.py` drew 60 random policies over 14 knobs (dividend rules, starting, par,
selling, cash reserve, own-share bonus, routing weights) and scored each against the
equilibrium population, every seating, 6 seeds, then re-scored the top 8 on 12 fresh seeds.

| Rules | Population | Best candidate (fresh seeds) | Incumbents |
|---|---|---|---|
| current | baron 82%, investor 18% | 33.5% | baron 33.3%, investor 33.4% |
| free_withhold | baron 40%, targeted 45%, investor 15% | 33.6% | 33.1-33.5% |

Nothing beats the equilibrium by more than 0.2 points. The top candidates are all investor
variants (`max_presidencies=0`, no cash reserve); their dividend knobs never apply. Within this
knob space the baron-plus-investor equilibrium has no exploit. The knob space does not yet
include presidency raids (buying control of a paying corporation), selling to fund better buys,
or a last-round IPO sweep; a human could try any of these.

## Capital interpolation

Same ten strategies, 6 seeds, 6,000 games each.

| Variant | Best responses (of 55) | Top mean shares | Replicator survivors | Mean table worth |
|---|---|---|---|---|
| baseline (float 8x) | baron 43 | baron 39 | baron 81%, investor 19% | 9,892 |
| float6 | early-builder 19, baron 18, baron-prestige 10 | early-builder 38.4, baron 38.3 | baron 82%, investor 18% (bootstrap: baron-prestige survives 13%) | 7,834 |
| incremental | baron 28, early-builder 18 | baron 38.2, early-builder 36.8 | baron 82%, investor 18% | 10,237 |
| float4 | early-builder 44, targeted 8 | early-builder 41.1 | targeted or early-builder alone | 5,271 |

Float capital moves the balance monotonically: 8x is paying-dominant, 4x is withholding-
dominant, and 6x splits the best responses almost evenly between early-builder and baron.
But even at 6x, baron still invades early-builder tables (35.5% ± 1.0) and not the reverse, so
the equilibrium is still baron plus investor. Incremental capitalization behaves like a milder
float cut with no worth penalty, and leaves baron dominant.

### float5, and what float capital can and cannot do

float5 (6,000 games): early-builder is the best response to 32 of 55 opponent pairs and has the
top mean share (40.1%, baron 39.6%), but the equilibrium is still baron (93% of bootstraps), and
table worth is 6,590.

The head-to-head that decides it, one strategy against two copies of the other:

| Float capital | early-builder invading barons | baron invading early-builders |
|---|---|---|
| 8x (current) | 26.7% ± 1.1 | 37.9% ± 0.7 |
| 6x | 30.2% ± 1.0 | 35.5% ± 1.0 |
| 5x | 31.3% ± 1.3 | 34.6% ± 1.4 |
| 4x | 35.9% ± 1.2 | 30.7% ± 1.3 |

The matchup moves smoothly and flips between 5x and 4x, but at no setting does each strategy
invade the other. Capital decides **which** plan wins; it does not make two plans coexist. At the
crossing point the two would be interchangeable, not complementary.

Coexistence needs a strategy that does better the rarer it is (as investor does: it needs
presidents to ride on). Investor is the only such strategy found so far. Candidates for a
mechanism that rewards being different: competition for the frontier (withholders need open
sky; a table of withholders fights over it), a market that punishes crowded trades, or a forced
corporate expense (the deferred piracy or Empire escalation) that only some plans pay well.

## Conclusions

1. Under the current rules **always-pay (baron) dominates**: best response to 79% of opponent
   pairs, equilibrium 82% baron plus an investor free rider at +1 point.
2. The web app's bot (`straight`) is the weakest builder in the stable.
3. Of the six rule variants, none produces two genuinely different viable strategies.
   free_withhold blurs paying and withholding into one plan; float capital swaps the winner.
4. No exploit of the baseline equilibrium exists within the bot's current knobs.
5. Next: a mechanism with negative frequency dependence, and richer bot plans (presidency
   raids, selling to fund buys) so the stable can find what a human would.
