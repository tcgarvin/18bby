18 BBY — Basic Economic Rules (Working Draft)

Design Goal

The base game should feel like a light 18xx / cube-rail game: deterministic, legible, and driven by route-building, corporate cash management, and network competition.

For this basic rules layer, ignore:

• trains / engines
• phases
• Empire escalation
• rebellion / unrest
• random events
• special powers beyond a few named-route exceptions

The core question is:

> Where should a corporation expand its network, and should it reinvest its income or pay dividends?

────────

1. Map and Network

• The map contains fixed planets connected by potential hyperspace routes.
• Planets are placed as part of the designed board, not randomly.
• Corporations begin at a homeworld.
• A corporation expands by paying from its treasury to build connected route segments outward from its existing network.
• Multiple corporations may use the same hyperspace corridors; routes do not block one another simply because they overlap.
• Some intersections or jump points may later support development such as Imperial security infrastructure.

Exact build costs and build limits are still TBD.

────────

2. Corporate Finance

• Each corporation has its own treasury, separate from player money.
• Corporations begin with fixed starting capitalization.
• Revenue may be:
  • Paid as dividends to shareholders, or
  • Withheld into the corporation treasury for future expansion.
• Stock-market behavior is still TBD, but paying and withholding should affect share value in a simple 18xx-style way.

────────

3. Revenue Is Based on Planet Pairs

Revenue is generated primarily by pairing planets served by the corporation.

Each planet may participate in at most one scored pair per operating round.

The corporation evaluates all planets reachable within its network and chooses the set of non-overlapping pairs that produces the most revenue.

This can be treated as a maximum-weight matching problem. A digital implementation may calculate the optimum automatically; a physical implementation should keep the pairing rules simple enough to reason about by inspection.

────────

4. Economic Planet Types

The current basic economy uses five types:

Agriculture

Food-producing and agricultural worlds.

Resources

Raw materials and strategic inputs, including:

• ores and metals
• doonium
• Tibanna gas
• coaxium
• rhydonium
• other mined or extracted materials

The rules do not need to distinguish these individual resources unless a special planet or named route does so.

Industry

General manufacturing, processing, and industrial production.

Shipyard

Major starship construction centers.

Shipyards are treated as their own category even though they are conceptually a specialized form of industry, because shipbuilding is thematically and economically important enough in Star Wars to deserve distinct treatment.

Market

A placeholder name for major consumer, commercial, or wealthy demand centers.

Examples may include worlds such as Coruscant or Cato Neimoidia.

“Market” is not necessarily the final name.

────────

5. Normal Trade Pairings

The exact pairing table is still under development, but the intended relationships are supply-chain relationships that should be immediately intuitive.

Current likely pairings include:

• Agriculture ↔ Market
  • Food and agricultural products flowing to major population / commercial centers.
• Resources ↔ Industry
  • Raw materials feeding manufacturing and processing.
• Resources ↔ Shipyard
  • Metals, gases, fuels, and strategic materials feeding shipbuilding.
• Industry ↔ Market
  • Manufactured goods flowing to consumer / commercial markets.
• Industry ↔ Shipyard
  • Components and manufactured systems feeding starship construction.

Additional pairings may be added only when their economic story is similarly obvious.

There is no requirement that every type have the same number of valid partners. Flexibility can instead be balanced through revenue values, map distribution, rarity, and geography.

────────

6. Basic Routes

After all desirable normal trade pairs are formed, any two remaining connected planets may be paired as a Basic Route.

• A Basic Route earns a small fixed amount, currently envisioned as roughly 5 credits.
• A Basic Route represents miscellaneous passenger, mail, freight, and local commercial traffic.
• Basic Routes are intentionally much less valuable than proper typed trade pairs.
• Basic Routes do not qualify for:
  • Core ↔ Outer Rim bonuses
  • security bonuses
  • named trade-route bonuses
  • other special trade modifiers

This keeps pairing as the fundamental unit of revenue without making unmatched planets completely worthless.

────────

7. Dual-Tag Planets

Some important worlds may have two economic tags.

Examples:

• Corellia — potentially Industry + Shipyard
• Kuat — potentially Industry + Shipyard or primarily Shipyard
• other major economic centers may receive similar treatment

A dual-tag planet provides flexibility but does not gain extra throughput.

> A planet may still participate in only one scored pair per corporation per operating round.

The corporation chooses whichever tag produces the best legal pairing.

────────

8. Regional Bonus

A normal typed trade pair whose endpoints lie in different major galactic regions may receive a bonus.

The current concept is:

• Core ↔ Outer Rim trade earns an additional bonus.

The exact regions and bonus amount are TBD.

Basic Routes do not qualify.

This is intended to reward long-distance interregional commerce without requiring per-segment distance calculations.

────────

9. Security Development

A later-but-compatible economic mechanism is Imperial security development at important jump points, intersections, or route locations.

Conceptually:

• A corporation may pay to develop a secure checkpoint / jump point.
• Normal trade routes passing through or terminating at that location may receive increased revenue because commerce is safer and more reliable.
• The corporation that developed the security point may receive a fee or subsidy when qualifying routes use it.
• The Empire / bank may pay these benefits rather than requiring direct payments between corporations.

Exact rules remain TBD.

Basic Routes should not qualify for security bonuses.

────────

10. Named Trade Routes and Special Pairs

A small number of thematic exceptions may appear on the map.

Examples include:

• Kessel Run
• Corellian Trade Spine
• other canonical named hyperspace routes or economically important connections

These may reward:

• connecting specific endpoints,
• using particular corridors,
• or satisfying a printed special condition.

Named routes should be rare enough to feel like landmarks rather than a second rules system.

Basic Routes do not qualify for named-route bonuses.

────────

11. Refining and Specialized Commodities

Refining exists thematically but is not currently a universal economic type.

For example, Kessel’s raw coaxium may support a special Kessel-to-refinery relationship, but the base game should not require every Resource route to pass through:

> Resources → Refinery → Industry → Shipyard

That would likely create too much supply-chain depth for the intended game weight.

Similarly, rare or famous commodities such as spice, beskar, cortosis, or kyber should generally be represented through:

• planet flavor,
• special rules,
• named routes,
• or scenario-specific effects,

rather than creating additional universal planet types.

────────

12. Military — Reserved for Later Empire Rules

Military is not currently one of the five basic economic planet types.

However, it is a strong candidate for a later Empire layer.

Possible future relationships include:

• Industry → Military
• Shipyard → Military
• specialized armaments production → Military

This could represent Imperial fleet bases, garrisons, fortress worlds, procurement centers, and the increasing militarization of the galaxy without complicating the vanilla economy.

────────

13. Current Design Principles

1. Pairing is the basic unit of revenue.
2. Every economic pairing should tell an obvious cargo story.
3. Planets do not need to be included merely because they are famous.
  • Economic relevance matters more than story prominence.
  • Backwater worlds such as Tatooine may simply be absent.
4. The five economic types are a ceiling to protect readability.
5. Asymmetry between types is acceptable.
  • Industry may be more flexible than Agriculture.
  • Balance should come from map design, values, and scarcity rather than forcing a symmetric pairing graph.
6. Major worlds may be dual-tagged, but every planet still scores only once per operating round.
7. Long-distance and special-route bonuses should reward interesting geography without creating route-calculation overhead.
8. The basic game should remain deterministic and low-randomness.

────────

Open Questions

• Final name for Market
• Exact legal trade-pair table
• Base revenue value of each typed pair
• Whether different typed pairings have different values
• Core / Outer Rim region definitions and bonus amount
• Build costs and build limits
• Starting capitalization
• Exact dividend / withholding / stock-price rules
• Security-development costs and payouts
• Named-route list and bonuses
• Final planet roster and tag distribution