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

Open http://localhost:5173. The Vite dev server proxies `/api` to `http://localhost:8000`.
The current game id goes in the URL as `?game=<id>`, so a reload returns you to the same game.
Games live in the API process's memory, so restarting the server ends them.

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Dev server with hot reload and the `/api` proxy |
| `npm run build` | Type-check (`tsc -b`) and build to `dist/` |
| `npm test` | Run the vitest unit tests (hex geometry, log diffing) |
| `npm run preview` | Serve the production build locally |

## Layout

- `src/api.ts`: the JSON contract's types and the fetch helpers.
- `src/hex.ts`: axial hex geometry, edge midpoints and region shading. Tested in `hex.test.ts`.
- `src/selectors.ts`: small derived views of the game state (grouping legal actions, prices).
- `src/logdiff.ts`: works out which log lines are new. The server sends only the last 200 lines,
  so the diff matches overlapping lines instead of comparing lengths.
- `src/colors.ts`: corporation, region and planet-type palettes.
- `src/components/`:
  - `HexMap`: the board. It draws region tints, neutral lanes for charted tiles, and a narrow
    trace per corporation on each lane it serves. Each corporation keeps its own offset, so
    traces stay continuous across tiles. It also draws planet badges, homeworld tags and,
    for the focused corporation, the scored pairs.
  - `NetworkActions`, `DividendActions`, `StockActions`: one control panel per phase.
  - `CorporationsPanel`, `PlayersPanel`, `StockTrack`, `LogPanel`, `GameOver`, `NewGame`.
  - `GameScreen`: layout and state for one game. `App` switches between screens and restores
    the game named in the URL.

## Map conventions

- Hexes are pointy-top axial `(q, r)`. The pixel center is
  `x = sqrt(3)·s·(q + r/2)`, `y = 1.5·s·r`. Exits `E SE SW W NW NE` have edge midpoints at
  0°, 60°, …, 300°, measured clockwise from +x with y pointing down.
- Each hex takes the region of its nearest planet. Ties go to Core, then Mid Rim, then Outer Rim.
- A corporation is in focus when you click its card or when it is operating. The focused
  corporation's traces and reachable planets are emphasized, and its scored pairs are drawn as
  arcs labelled with their value. Solid arcs are typed pairs; dashed arcs are basic routes.
