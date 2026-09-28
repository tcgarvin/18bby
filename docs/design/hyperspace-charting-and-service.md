18 BBY — Hyperspace Charting and Service

Design Intent

The hyperspace map uses fixed planets separated by buildable space hexes.

Corporations do not build private physical routes. Instead:

• Charting creates and upgrades the shared hyperspace network.
• Service determines which parts of that shared network a corporation can use.
• Pairing determines which reachable planets generate revenue for that corporation.

This preserves the existing planet-pair economy while giving the map meaningful spatial structure and competition.

────────

1. Hyperspace Tiles

Empty space hexes begin uncharted.

When a corporation charts an uncharted hex, it places a hyperspace tile with exactly two connected exits.

Because the game is digital, there is no limited physical tile inventory. Any legal orientation of a two-exit tile may be placed.

Examples include:

• straight connections,
• bends,
• or any other two-edge configuration allowed by hex geometry.

────────

2. Charting Upgrades

A previously charted two-exit hex may be charted again to upgrade it to a three-exit tile.

The new tile must preserve the existing connections and add one additional exit.

For the initial ruleset, only two charting levels are required:

• Level 1: two exits
• Level 2: three exits

A later version may allow a four-exit upgrade, potentially at additional cost, but this is not part of the initial design.

────────

3. Shared Network

Charted hyperspace tiles are part of a shared galactic network.

The geometry of a tile is not owned by the corporation that charted it. Other corporations may later establish service through the same charted hex.

For now, there is no limit on how many corporations may establish service on the same tile.

If playtesting shows that corporations too often use identical networks, capacity limits, congestion, escalating costs, or other restrictions may be added later.

────────

4. Corporate Service

Each corporation has its own service network layered on top of the shared hyperspace network.

A corporation may establish service on a charted tile only if that tile is connected to the corporation’s existing service network.

When a corporation is the first to chart an uncharted hex, it automatically establishes service on that tile.

This ensures that the corporation paying to expand the shared network immediately benefits from doing so.

A corporation may also extend service onto an already-charted tile without being the corporation that originally charted it, provided normal connectivity requirements are satisfied.

The exact action cost and monetary cost of extending service remain TBD.

────────

5. Reachability

A planet is considered reachable by a corporation if it can be connected to that corporation’s existing network through a continuous path of charted tiles on which that corporation has service.

Only planets reachable through that corporation’s service network are available for its revenue calculation.

The shared hyperspace geometry therefore answers:

> Where can commercial traffic potentially travel?

Corporate service answers:

> Which parts of that network does this corporation actually operate?

────────

6. Revenue Pairing

The existing planet-pair revenue system remains in place.

During revenue calculation, a corporation considers only planets reachable through its own service network.

Those reachable planets are then paired according to the normal economic pairing rules.

Each planet may still participate in at most one scored pair per operating round.

Introducing hyperspace tile geometry therefore does not require switching to a train-style route-scoring system.

────────

7. Digital Presentation

Hyperspace lanes should be visually distinct from corporate service.

A likely presentation is:

• broad or neutral-colored hyperspace lanes showing the shared charted network,
• narrower corporation-colored traces layered along those lanes showing where each corporation has service.

Multiple corporation colors may appear on the same charted lane.

When a corporation is selected, the interface should emphasize that corporation’s service network and the planets it can reach.

Scored or candidate economic pairs should generally be shown only when relevant to revenue calculation rather than permanently drawn across the map.

────────

8. Current Open Questions

The following details remain to be determined through further design and playtesting:

• charting cost,
• service-extension cost,
• how many charting and/or service actions a corporation may take per operating turn,
• whether charting and extending service compete for the same action allowance,
• whether three-exit upgrades cost more than initial charting,
• whether four-exit tiles are eventually needed,
• whether shared tiles need corporation capacity limits,
• whether builders receive any additional benefit beyond automatic first service.

The initial prototype should avoid adding these restrictions until playtesting demonstrates a need for them.