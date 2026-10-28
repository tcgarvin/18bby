# Screenshot harness

Screenshots of the real UI for visual design work. From the repository root:

```sh
uvx --with playwright==1.63.0 python web/scripts/screenshots/shoot.py [OUT_DIR] \
    [--seed 7] [--round 7] [--min-tiles 20] [--scale 2]
```

It starts the API (`BBY18_MODE=local`) and a Vite dev server on free ports (so it never clashes
with `npm run dev`; `vite.config.mjs` here is that server's config), creates a game with one human
seat and three easy bots, plays the human seat through the engine's legal actions (prefers buying
at the highest par, then charting, upgrading, servicing, facilities) until the round and tile
thresholds are met, and shoots the first stop in each phase. Servers are stopped on exit. Takes
about 15 seconds; the same seed gives the same game.

Output (default `OUT_DIR` is in the session scratchpad), named `<phase>-<round>`:

- `<phase>.png`: 1600x1000 view for `stock`, `network`, `fleet` (facilities) and `dividend`.
- `<phase>-map.png`: the map alone at `--scale` device pixels. Network and fleet use the inline
  map; the other views only have a thumbnail, so their crop is the whole map overlay panel (M key), legend included.

Playwright 1.63 matches the cached Chromium build (revision 1243) in `~/.cache/ms-playwright`;
`uvx` fetches the Python package once. The human only operates CEC from round 7 on (the bots
float the other corporations first), hence the late default round. If a phase is not reached the
script says so on stderr; try another `--seed` or lower `--round`.
