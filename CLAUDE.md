# 18BBY — working notes for Claude

Rules engine and playtest harness for an 18xx-style Star Wars game. Python 3.11, managed with
`uv`. Run `uv run pytest`, `uv run mypy src`, and `uv run black src tests` before finishing work.

## Where things live

- Rule decisions and their rationale: `docs/DECISIONS.md`. Update it whenever a rule changes.
- Original design docs: `docs/design/`. Do not edit these; they are the designer's source material.
- All tunable numbers: `src/bby18/config.py`. Never hardcode a cost, value, or limit elsewhere.
- Rule enforcement: `src/bby18/game.py` and `src/bby18/network.py`. Drivers and bots decide what
  to do; these modules decide whether it is legal and apply the consequences.

## Conventions

- Planets are open hubs: every exit, no charting, no service cubes. See `network.py`.
- Hex coordinates are axial `(q, r)`, pointy-top, matching `docs/design/hex-map-design.md`.
- Bots must only choose from the legal action lists the engine provides.
- Keep the game end condition isolated in `Game.is_over` so an in-universe trigger can replace
  the fixed round count later.
