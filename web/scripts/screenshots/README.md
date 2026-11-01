# Screenshot harness

Screenshots of the real UI for visual design work. From the repository root:

```sh
uvx --with playwright==1.63.0 python web/scripts/screenshots/shoot.py [OUT_DIR] \
    [--seed 7] [--round 6] [--min-tiles 24] [--min-chains 2] [--scale 2]
```

It starts the API (`BBY18_MODE=local`) and a Vite dev server on free ports (so it never clashes
with `npm run dev`; `vite.config.mjs` here is that server's config), creates a game with one human
seat and three very easy bots, and plays the human seat until the game is well developed: from
round `--round` (0 = SR1, so 6 is SR7 and OR7), with at least `--min-tiles` tiles and the human's
corporation running at least `--min-chains` supply chains. It then shoots the first stop in each
phase. Servers are stopped on exit. Takes about 30 seconds; the same seed gives the same game.

The human only ever plays an action the engine lists as legal:

- **Stock:** starts one corporation at the lowest par and buys it until it floats, then passes.
  It has to float alone: the bots start their own corporations and rarely buy into another's, and
  the starting cash reaches the shares a float needs only at the lowest par.
- **Network:** builds toward the nearest hub it has not reached, keeping a facility's price back.
- **Facilities:** builds whatever earns the most, but stays one short of the limit until the
  facility step has been shot, because the session skips that step at the limit.
- **Dividends:** withholds, and pays once the treasury holds 200.
- **Seizures:** surrenders the facility whose loss costs the least.

Output (default `OUT_DIR` is in the session scratchpad), each name starting `<phase>-<round>`,
such as `network-OR7.1`, written `<phase>` below:

- `<phase>.png`: 1600x1000 view for `stock`, `network`, `fleet` (facilities) and `dividend`.
- `<phase>-map.png`: the map alone at `--scale` device pixels, with its Regular | Routes toggle.
  Network and fleet use the inline map; the stock round crop switches to the read-only Map view
  (M key), and the dividend crop is its zoomed map.
- `<phase>-routes.png`, `<phase>-map-routes.png`: the same with the map on Routes, after which the
  toggle goes back to how it was. The stock round's map has no corporation in focus and Routes
  needs one, so its Routes shots are of the Map view with the human's corporation picked.
- `dividend-<round>-map-regular.png`: the dividend map on Regular. That view starts on Routes, so
  its `-routes` shots match its plain ones.

The Routes shots are skipped when the toggle is missing or Routes is disabled. The last lines of
the output say, for each phase, whether they were taken and why not. A skip does not fail the run.

If a phase is not reached the script names it on stderr and exits 1; try another `--seed` or lower
the thresholds. Of seeds 1-30, 19 reach every phase at the default thresholds (1, 2, 5, 6, 7, 8,
10, 11, 12, 15, 16, 17, 18, 21, 23, 24, 26, 28, 30). In the others the game ends too soon or the
human's corporation stays on one chain.

Playwright 1.63 matches the cached Chromium build (revision 1243) in `~/.cache/ms-playwright`;
`uvx` fetches the Python package once.
