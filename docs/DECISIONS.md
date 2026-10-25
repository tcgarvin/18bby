# 18BBY — Day-One Rule Decisions

Recorded 2026-09-27. These settle the questions the design docs leave open so that the
engine can run complete games. Every numeric value lives in `bby18/config.py` as a tunable
and is expected to change with playtesting. Rules marked **placeholder** were chosen for
expedience, not conviction.

## Player count

- **Three players is the design target** (decided 2026-09-28). Balance work tunes for three
  players and checks four. The engine still runs two-player games, but they are not
  balanced: with two corporations the game is a mirror match decided by a few credits of
  dividends, and fixing that is deferred.

## Map and network

- **Board:** the 127-hex "Room for junctions" map (`docs/design/hex-map-design.md`), loaded
  from `src/bby18/data/map-127.json`.
- **Planet hexes are open hubs.** A planet hex permanently has all six exits. Any charted tile
  with an exit facing a planet connects to it. A corporation's network may pass through a
  planet freely. Planets never need charting and carry no service cubes: a corporation
  "has service" at a planet whenever the planet is reachable through its network.
- **Tile exits** must face on-board hexes. Any two distinct legal exits form a level-1 tile;
  an upgrade adds one more exit and preserves the existing two.
- **Connection** between two adjacent hexes requires each side to have an exit facing the
  other (planets always do).
- **Reachability** for a corporation is a breadth-first walk from its homeworld across
  connected hexes, where a space hex is passable only if the corporation has service on it.

## Corporations

- **Four corporations** (placeholder, chosen for fast playtests):

  | Corp | Homeworld | Region |
  |---|---|---|
  | Corellian Engineering Corporation (CEC) | Corellia | Core |
  | Kuat Drive Yards (KDY) | Kuat | Core |
  | Coruscant Shipping Consortium (CSC) | Coruscant | Core |
  | Kashyyyk Trade Guild (KTG) | Kashyyyk | Mid Rim |

  Names are flavor placeholders. A corporation's homeworld is always reachable by it.

## Operating turn

Each operating turn a corporation, in order:

1. Takes **up to two network actions** (placeholder allowance): chart an uncharted hex,
   upgrade a charted tile it has service on to three exits, or extend service onto one
   already-charted tile adjacent to its network. Charting and service cost **50**; an
   upgrade costs **70** (see "Terrain and expansion cost"). Passing ends the corporation's
   network actions for the turn. (History: one action at cost 20 until 2026-09-28; service
   was 10 until 2026-09-27, when bot playtests showed nearly every tile shared; upgrades cost
   50 until 2026-10-25.)
2. Has its **revenue** computed automatically (see Economy).
3. Chooses to **pay** the full revenue as dividends or **withhold** it into the treasury.

Charting and upgrading require the tile to connect to the corporation's reachable network.
First charting grants service automatically. Upgrading requires the corporation already to
have service on the tile.

## Economy

- **Typed pairs:** Agriculture↔Market, Resources↔Industry, Resources↔Shipyard,
  Industry↔Market, Industry↔Shipyard. Each earns a flat **30**.
- **Regional bonus:** a typed pair with one endpoint in the Core and one in the Outer Rim
  earns **+20**.
- **Basic route:** any two remaining reachable planets earn **5**. No bonuses.
- **Matching:** the engine computes a maximum-weight matching over all reachable planets.
  Each planet scores at most once per corporation per operating round. Dual-tag planets
  use whichever tag yields the better matching.
- **Dividends:** revenue is split into ten per-share amounts (rounded down). Shares held by
  players pay their holders. Shares in the IPO or the bank pool pay **nobody**; that money and
  the rounding remainder stay with the bank. (Until 2026-09-28 unheld shares paid the
  treasury, which the balance sweep found was a dead sink that was never spent.)

## Stock market

- **Two-dimensional market** (adopted 2026-09-28, replacing a linear track; grid values are
  placeholders in `config.py`). Eight rows, top row highest; moving up one row is worth about
  one column to the right. Lower rows end sooner (the bottom row tops out at 110, the top
  row at 400).
- **Par** chosen by the president from `60, 70, 80, 90, 100`, all in one par column
  (column 4), with two rows below the lowest par so sales can always push a price down.
- **Paying dividends moves the price right by payout size:** one column if revenue is at
  least half the share price, two columns if it is at least 1.5 times the share price, no
  move below half. At the end of a row a right move goes up instead.
- **Withholding** (including a zero-revenue turn) moves it left one column; at the left
  edge it goes down instead.
- **Each share sold to the pool** moves it down one row, stopping where the row below ends.
- **Sold out:** at the end of each stock round, a started corporation with no shares left in
  the IPO or the pool moves up one row.
- **Why:** the 2026-09-28 balance sweep found the linear track was a pay counter. Every
  corporation that never withheld ended at exactly 230 whatever it earned, so selling,
  withholding and par choice had no effect on price. The 2-D market ties the horizontal
  move to earnings and the vertical move to demand, the classic 18xx split.
- **Capitalization:** ten shares, president's certificate is 20%. When 50% of shares have
  been sold, the corporation floats and receives **eight** times par from the bank (ten times until 2026-09-28).
- **Operating order:** descending share price; ties by float order.

## Stock round

Players in priority order may sell any number of shares to the pool (not in the first
stock round), then buy one share from the IPO at par or from the pool at market price, or
pass. The round ends when every player passes in succession. Priority passes to the player
after the last one who bought or sold.

- **Holding limit:** 60% of any corporation. **Certificate limit:** 12.
- **President:** must hold at least 20%; the presidency transfers to the largest
  holder if they exceed the president's holding.
- **Starting cash** (placeholder): 2 players 600, 3 players 400, 4 players 300. Kept below
  about 430 per player at three players: above that, seat 1 wins on buy order alone.

## Game length

- **Fixed rounds** (placeholder): six repetitions of one stock round followed by two
  operating rounds. The end condition is an isolated strategy so an in-universe trigger
  (Empire escalation, rebellion, and so on) can replace it later without touching round
  logic.
- **Final score:** cash plus share value at final market price.

## Capital is meant to bind (decided 2026-09-28)

A corporation should not be able to build every turn and pay every dividend. The 2026-09-28
sweep found money never ran short: a corporation floated with 600 and could spend at most 240,
so withholding was never worth a price step. The fix adopted together: two network actions
per turn, action cost 50 (from 20), float capital eight times par (from ten), and unheld
shares paying nobody. In bot playtests a corporation now withholds roughly one turn in three
and still builds almost every action. Slightly over-tight is acceptable: a slow game leaves
room for later features that inject money. Player starting cash was left alone because it
did not bind corporate spending in any tested setting.

## Terrain and expansion cost (decided 2026-10-25)

The starlane game was too easy: with every hex alike and every build 50, the only decision
was which planets to link. Two changes make routing a puzzle. Both are tunable in
`config.py`, and sweeps can switch either off to compare.

- **Asteroid fields** (15% of non-planet hexes) are impassable. They cannot be charted, and
  no tile may have an exit facing one, so routes bend around them.
- **Nebulae** (15% of non-planet hexes) cost **+30** to chart (80 instead of 50). Extending
  service onto an existing nebula tile costs the usual 50, so the first company through
  pays and rivals ride cheaply. A nebula tile can **never be upgraded** to three exits.
- **Placement is seeded.** The game seed alone fixes the layout (`terrain.py`), so a seed
  always gives the same sky and a saved game's replay rebuilds it. Terrain comes in random
  patches of up to three hexes (`terrain_patch_size`; 1 scatters single hexes). Asteroids are
  placed first, and a hex that would cut any planet off from the rest is skipped, so the
  planets always form one connected whole. Planet hexes never carry terrain. Symmetry between
  seats is not required: players choose corporations, not positions.
- **Charting is exploration, the 2-to-3-exit upgrade is expansion.** Charting places a
  two-exit tile for **50**; the only upgrade, to three exits, now costs **70** (was 50).
  Upgrades in open space otherwise work as before.
- **Existing saved games** replay from their seed, so they now rebuild with terrain and the
  70 upgrade. A save whose recorded moves are no longer legal is reported as outdated.

Terrain is measured by the sweep harness, not decided by it: `bby18 terrain-report` prices
planet pairs on the map alone, and sweep rows carry per-planet value and reach, near-pair
links and frontier costs. The `greedy-path` bot prices routes around terrain; the original
`greedy` bot measures straight-line hexes and does not.

## Explicitly deferred

Empire escalation, rebellion, security development, named trade routes, military planets,
four-exit tiles, tile capacity limits, and any builder benefit beyond first service.

Also deferred, from the 2026-10-25 terrain discussion: **piracy** on the busiest hex at the
end of a turn (a traffic-based tax or raid; it needs rules for ties, who pays, and who
controls the pirates), and a player-run pirate faction such as the Black Sun as an expansion.
Terrain concentrates traffic into chokepoints, so it should come first.
