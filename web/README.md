# 18BBY web frontend

A browser UI for hotseat games of 18BBY: Vite, React and TypeScript, with the map drawn in SVG.
It talks to the FastAPI server in `src/bby18/api/` and holds no rules of its own. Every action
the UI submits is one of the server's `legalActions`, sent back unchanged.

## Setup

Requires Node 20+ and the Python project set up with `uv sync` (see the root README).

```sh
cd web
npm install
```

## Run

In one terminal, start the API from the repository root:

```sh
uv run bby18 serve --port 8000
```

In another, start the dev server:

```sh
cd web
npm run dev
```

The API serves the Death Star and fleet rules, the default since 2026-10-26 (see
`docs/DECISIONS.md`). It serves whatever `DEFAULT_CONFIG` in `src/bby18/config.py` says: with
`facility_rules` on it serves the experimental facility rules instead, and the UI follows the
state it is sent (a `facilities` block, and `deathStar.fleets.item` of `"facility"`).

Open http://localhost:5173. The Vite dev server proxies `/api` to `http://localhost:8000`.
The current game id goes in the URL as `?game=<id>`, so a reload returns you to the same game.
The home screen lists your saved games. Locally the server keeps them in memory, so restarting
it ends them; the deployed site saves them in Postgres (see `docs/DEPLOYMENT.md`).

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Dev server with hot reload and the `/api` proxy |
| `npm run build` | Type-check (`tsc -b`) and build to `dist/` |
| `npm test` | Run the vitest unit tests (hex geometry, selectors, replay frames and timing) |
| `npm run preview` | Serve the production build locally |

## Layout

- `src/api.ts`: the JSON contract's types and the fetch helpers.
- `src/auth.ts`: the anonymous account token, created on first use and kept in localStorage.
- `src/hex.ts`: axial hex geometry, edge midpoints and region shading. Tested in `hex.test.ts`.
- `src/selectors.ts`: derived views of the game state: legal trades per corporation, the
  round stepper, the operating order with who is done, dividend payouts.
  Tested in `selectors.test.ts`.
- `src/deathstar.ts`: derived views of the Death Star rules (the state's optional
  `deathStar` block): the active and reserved sites, cubes per stage, what the next stage does,
  when the game ends, the fleet supply, a corporation's fleet-step options, the seizure it should
  plan for, and how many of its pairs its fleets run. Tested in `deathstar.test.ts`.
- `src/facilities.ts`: derived views of the facility rules (the state's optional `facilities`
  block): which lanes run into a planet (only through claimed exits), the legal builds grouped by
  planet with the server's preview of each, the facility the next seizure takes, facilities that
  turned Imperial, planets to outline after others' moves, and whether a new lane claims a
  planet's exit or dangles. Tested in `facilities.test.ts`.
- `src/tilediff.ts`: which hexes changed between two states, for outlining others' moves.
  Tested in `tilediff.test.ts`.
- `src/hotkeys.ts`: the `useHotkeys` hook behind the keyboard shortcuts. Tested in
  `hotkeys.test.ts`.
- `src/logdiff.ts`: works out which log lines are new. The server sends only the last 200 lines,
  so the diff matches overlapping lines instead of comparing lengths.
- `src/colors.ts`: corporation, region and planet-type palettes.
- `src/terrain.ts`: seeded scatter of rocks and wisps, so an asteroid or nebula hex always draws
  the same. The terrain itself comes from the server's per-game `terrain` list. Tested in
  `terrain.test.ts`.
- `src/playback/`: replays opponents' moves (the state's `moves`) as animations.
  - `frames.ts`: pure. `playbackSteps(before, after)` turns a reply's move frames into steps:
    one per automatic move (the submitted move is applied but not shown) and a banner wherever
    the round changes. Each step's `state` is the game after the move, still in the move's own
    phase and turn, so a dividend shows on the dividend view. `moveKind` summarises a move from
    the change it made (who paid what, price before and after); `describeMove` captions it.
    Tested in `frames.test.ts`.
  - `timing.ts`, `player.ts`: how long each kind of step shows (scaled by speed, with a minimum
    when a step switches views) and the timer-driven queue, timed from when each step is on
    screen. The speed is kept in localStorage. Tested in `player.test.ts`.
  - `usePlayback.ts`: the hook GameScreen uses: `enqueue(before, after)`, `display`, `current`,
    `skip`, `setSpeed`.
  - `FlightLayer.tsx`, `flight.ts`, `choreography.ts`, `StepEffects.tsx`: an overlay that flies
    share certificates and coins between the anchors below, pops labels and rings highlights;
    `choreography.ts` says which effects each kind of move plays. Tested in `flight.test.ts`.
  - Under the Death Star rules, `frames.ts` also captions fleet buys and finishes, notes cubes a
    move put on the track, and adds an `empire` step after any move whose round end applied a
    stage (seizure, site move, launch) or that left a corporation bankrupt, even after your own
    move. Tested in `deathstar.test.ts`. Under the facility rules it captions facility builds
    (where, and which lane got the new exit), merges each frame's changed planets, and names the
    facilities a seizure turned Imperial. Tested in `playback/facilities.test.ts`.
  - `ReplayBar.tsx` (caption, counter, speed, Skip; the round banner), `Ticker.tsx` (numbers
    that tick to a new value), `useSettled.ts` (show a "before" value for one frame so a newly
    mounted view still animates the change).
- `src/components/`:
  - `GameScreen`: the container for one game. It owns the server state, sends actions and undo,
    and keeps errors and the "since your move" ribbon. It draws a `display` state, which the
    replay engine may hold on an intermediate state while it animates; the view is chosen from
    `display.phase` alone, and controls appear only when the display is the latest state and a
    human is to move (`interactive`). `App` switches between screens and restores the game named
    in the URL.
  - `views/`: one presentational view per phase, all taking `ViewProps` (`views/types.ts`):
    `StockRoundView`, `NetworkView`, `FleetView` (Death Star rules: buy fleets, with
    `FleetActions` in the operating rail), `FacilityView` (the same step under the facility rules:
    pick a planet on the map or in `FacilityActions`, then where its new exit goes),
    `DividendView`, `GameOverView`.
  - `TopBar` (round stepper, who is acting, overlay toggles, Undo), `RecentMoves` (the ribbon),
    `Overlay` and `MapOverlay` (the map, market and log over any view).
  - `PlayerStrip` (player cards, or a compact cash strip), `CorporationBoard` (corporation cards
    with IPO and pool certificate stacks and the inline buy, sell and par buttons), `CertStack`
    (a small pile of share certificates with its share count; the president's certificate is
    wider, gold-framed and starred; used on corporation and player cards, dividend payouts and
    the final standings, and copied by the flight layer for a share in flight), `StockMarket` (the grid, or a
    slice of it, with tokens positioned from their cell so they can slide), `OperatingRail` (the
    operating order, with the current corporation's panel), `NetworkActions`, `GameOver`.
  - `HexMap`: the board. It draws region tints, neutral lanes for charted tiles, and a narrow
    trace per corporation on each lane it serves. Each corporation keeps its own offset, so
    traces stay continuous across tiles. It draws asteroid fields and nebulae, planet badges,
    homeworld tags and, for the focused corporation, the scored pairs. It can zoom to a set of
    hexes (`fitHexes`). Under the facility rules a lane runs into a planet only through a claimed
    exit, a lane facing a planet without one ends in a red bar (dangling), open exits are small
    rings above the planet, and facilities are small squares in their owner's colour beside it
    (a purple diamond once Imperial); a new or seized facility pops in. `MapLegend`,
    `MapThumbnail` and `TilePreview` go with it.
  - `Help`: the "?" glossary popover. It renders in a portal on `document.body` with fixed
    coordinates from the trigger (`src/popover.ts`, tested in `popover.test.ts`): below the
    "?", flipped above when there is no room, clamped inside the window, and above overlays and
    the flight layer, so no panel can clip it.
  - `DeathStar`: under the Death Star rules, `DeathStarBar` (a strip under the top bar with the
    track's cubes per stage, the stage being built, its contract value and result, when the game
    ends, and the fleet price), `FleetIcons` (a corporation's fleets up to the limit) and the
    station glyph the map draws on the active site. Everything in it is hidden when a game has no
    `deathStar` block.
  - `LogPanel`, `NewGame`, `SavedGames` (the "your games" list on the home screen),
    `RulesPage`.

### Animation anchors

The views mark the things that change with `data-*` attributes, which the replay engine looks
up (`src/playback/flight.ts`): `data-player-id` (player card), `data-cash-for` (a player's cash),
`data-corp-id` (corporation card, or its operating-order entry), `data-ipo-for` (the IPO
certificate stack), `data-pool-for` (the pool stack, present only while the pool holds shares;
effects fall back to the corporation card), `data-treasury-for`, `data-market-token` (a corporation's stock market token),
`data-order-corp` (operating-order entry), `data-hex="q,r"` (a map hex), and under the Death
Star rules `data-fleets-for` (a corporation's fleet icons, or its facility icons under the facility
rules), `data-fleet-supply` and
`data-death-star-track` (on the Death Star bar). Each appears at most
once per view; second copies in overlays leave them off. The `caption-slot` at the bottom of
the stage holds the replay caption.

What each kind of move animates (`src/playback/choreography.ts`): a buy flies a share certificate
(the president's certificate when it starts a corporation) from the IPO or pool to the buyer and pops the cost at their cash (and the treasury gain when it
floats); a sale flies the certificates to the pool and lights the market token; a build flies a coin
from the treasury to the hex, where the new lane draws in and glows in the builder's colour; a
dividend flies a coin to each paid player's cash, or pops the withheld sum at the treasury, and
lights the market token; a fleet buy flies a coin to the fleet price on the Death Star bar and
lights the corporation's fleets; a facility build flies a coin to the planet and lights it and the
builder's facilities; a seizure pops "−1 fleet" (or "−1 facility", lighting each seized planet) on
each corporation that lost one, a site move lights the old and new hexes, and a bankruptcy pops on
the corporation. Cash, treasury and prices tick to their new values, and market tokens
slide between cells.

## Playing

The screen changes with the phase; the top bar shows where you are (e.g. SR4 › OR4.1 › OR4.2)
and who is acting.

- **Stock round:** the players and what they hold across the top, the corporations below with
  their price, treasury and president, and stacks of the certificates for sale in the IPO and
  the pool. Each player card shows the certificates that player holds. On your turn each
  corporation shows the buys, sells and pars you may make, and **Pass** sits at the top. The
  stock market sits beside them, and a small map opens the full map.
- **Operating, building:** the map fills the screen. The operating order runs down the right,
  done, operating, then up next; the operating corporation's entry holds its network options.
  Click a highlighted hex to see its tile options, or an entry to show that network on the map.
- **Operating, dividend:** the corporation's revenue and its scored pairs, with Pay and Withhold
  side by side: what each shareholder receives, the treasury, and where the share price moves
  (marked on a slice of the market). The map shrinks to the corporation's network.
- **Operating, fleets (Death Star rules):** after the network actions the corporation buys fleets
  from the shared supply. The rail's entry shows its fleets, the next fleet's price and what it
  adds to this turn's revenue, and warns when a coming seizure would leave it unable to replace
  its only fleet. <kbd>B</kbd> buys, <kbd>P</kbd> finishes. The Death Star bar under the top bar
  shows the track, the contract value and when the game ends throughout; the map draws the site
  (W) and the dashed future site, and dotted arcs mark contract pairs.
- **Operating, facilities (facility rules):** fleets are replaced by facilities on planets. The
  map highlights the planets the corporation may build on; pick one there or in the rail's list
  (<kbd>1</kbd>–<kbd>9</kbd>), then choose where its new exit goes: left open, or given to a lane
  that dangles there (<kbd>1</kbd>–<kbd>9</kbd>). Each choice says what it adds to this turn's
  revenue and whose lane it connects, and hovering one previews it on the map. <kbd>P</kbd>
  finishes, <kbd>Esc</kbd> closes the planet. In the network step, a chart or upgrade option
  facing a planet says whether it claims an exit there or dangles.
- **Map, market and log** open over any view that does not already show them: <kbd>M</kbd>,
  <kbd>K</kbd>, <kbd>L</kbd> or the top-bar buttons; <kbd>Esc</kbd> closes.
- **Undo** (top bar, <kbd>U</kbd> or <kbd>Ctrl</kbd>+<kbd>Z</kbd>) takes back your last move,
  along with every bot move and forced move that followed it. It goes back as far as the game
  began; in a hotseat game it takes back whoever moved last.
- **Opponents' moves replay.** After your move, each bot or forced move plays out in turn on the
  view for its phase: share certificates and coins fly, new lanes draw in, and a bot's dividend shows
  the card it chose. A caption at the bottom says what happened, with a counter. Pick the speed
  there (1×, 2×, 4×, 8× or Off, which shows the result at once); the choice is remembered.
  **Skip** (<kbd>Space</kbd> or <kbd>Esc</kbd>) jumps to the end. Other shortcuts and Undo are
  paused while a replay runs. A new game's opening bot moves are not replayed; they are listed
  in the ribbon.
- **Forced moves play themselves.** When the only legal choice is to pass, take no network
  action, or withhold zero revenue, the server plays it, and it replays with the bots' moves.
- **The "Since your move" ribbon** under the top bar sums up the last batch once it has played
  (straight away when replay is Off). It has the speed picker and **watch again**.
- **Others' moves are outlined on the map** once the replay is over. Hexes that bots (or forced
  moves) changed since your move get an outline in the colour of the corporation that gained
  service there. It stays until the next batch of automatic moves, or until you hide the ribbon.
- **Keyboard:** <kbd>P</kbd> passes in a stock round and ends network actions; with a hex
  picked, <kbd>1</kbd>–<kbd>9</kbd> choose a tile option and <kbd>Esc</kbd> closes the picker
  (or clears the map focus); in the dividend step <kbd>1</kbd> pays and <kbd>2</kbd> withholds.
  Shortcuts are ignored while typing in a form field, and the view's own shortcuts pause while
  an overlay is open.

## Map conventions

- Hexes are pointy-top axial `(q, r)`. The pixel center is
  `x = sqrt(3)·s·(q + r/2)`, `y = 1.5·s·r`. Exits `E SE SW W NW NE` have edge midpoints at
  0°, 60°, …, 300°, measured clockwise from +x with y pointing down.
- Each hex takes the region of its nearest planet. Ties go to Core, then Mid Rim, then Outer Rim.
- A corporation is in focus when you click its operating-order entry (or its button in the map
  overlay) or when it is operating. The focused
  corporation's traces and reachable planets are emphasized, and its scored pairs are drawn as
  arcs labelled with their value. Solid arcs are typed pairs; dashed arcs are basic routes.
