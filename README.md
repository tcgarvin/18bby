# 18BBY

An 18xx-style game of hyperspace commerce set in the Star Wars galaxy, 18 years before the
Battle of Yavin. Corporations chart a shared hyperspace network, establish service on it, and
earn revenue by pairing the planets they can reach.

This repository holds the rules engine and a bot playtest harness. A digital board UI is a
later milestone.

## Layout

- `docs/design/` — the source design documents (economic rules, charting and service, map).
- `docs/DECISIONS.md` — the day-one rule decisions that fill the gaps the design docs leave open.
- `src/bby18/` — the engine.
  - `hexgrid.py` axial hex coordinates; `board.py` the fixed map; `network.py` shared tiles and
    per-corporation service; `revenue.py` planet-pair matching; `market.py` the stock track;
    `game.py` rule enforcement; `runner.py` round sequencing; `bots/` automated players;
    `playtest.py` and `cli.py` the harness.
  - `config.py` holds every tunable number.
- `tests/` — pytest suite.

## Setup

```sh
uv sync
uv run pytest
uv run mypy src
uv run black src tests
```

## Playtesting

```sh
uv run bby18 playtest --games 50 --players 3          # aggregate stats over many bot games
uv run bby18 playtest --bots random --games 20        # random-play baseline / fuzzing
uv run bby18 replay --seed 7                          # full log of one game
```

Change values in `src/bby18/config.py` (or construct a `GameConfig`) to test rule variants.
