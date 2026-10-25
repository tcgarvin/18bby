# 18BBY — working notes for Claude

Rules engine and playtest harness for an 18xx-style Star Wars game. Python 3.11, managed with
`uv`. Run `uv run pytest`, `uv run mypy src`, and `uv run black src tests` before finishing work.

## Where things live

- Rule decisions and their rationale: `docs/DECISIONS.md`. Update it whenever a rule changes.
- Original design docs: `docs/design/`. Do not edit these; they are the designer's source material.
- All tunable numbers: `src/bby18/config.py`. Never hardcode a cost, value, or limit elsewhere.
- Hosting, sign-in and saved games: `docs/DEPLOYMENT.md`. The API is stateless; games are
  loaded from and written to a `GameStore` on every request.
- Postgres store tests skip unless `BBY18_TEST_DATABASE_URL` names a throwaway database; see
  `docs/DEPLOYMENT.md` for a one-line Docker Postgres.
- Strategy bots for balance work: `src/bby18/bots/stable.py` (one line per archetype) and
  `src/bby18/tournament.py`. A sweep spec with `"tournament": "stable"` plays every lineup in
  every seat order; `bby18 tournament-report --rows rows.jsonl` finds best responses and
  equilibria. The balance goal is no single dominant strategy, not equal win rates.
- Web opponents: named characters in `src/bby18/bots/roster.py`, each a stable strategy with a
  per-difficulty `noise` from `BOT_NOISE` in `config.py`. Recalibrate with
  `docs/sweeps/difficulty-2026-10-25` when the rules or a strategy change.
- Rule enforcement: `src/bby18/game.py` and `src/bby18/network.py`. Drivers and bots decide what
  to do; these modules decide whether it is legal and apply the consequences.

## Conventions

- Planets are open hubs: every exit, no charting, no service cubes. See `network.py`.
- Hex coordinates are axial `(q, r)`, pointy-top, matching `docs/design/hex-map-design.md`.
- Bots must only choose from the legal action lists the engine provides.
- Keep the game end condition isolated in `Game.is_over` so an in-universe trigger can replace
  the fixed round count later.
