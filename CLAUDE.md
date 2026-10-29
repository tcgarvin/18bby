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
- Death Star rules in sweeps: the rules are the default (with facilities since 2026-10-27, six
  corporations and Coruscant's +10 pair bonus since 2026-10-28), so a spec variant `{}` plays
  them; seat `strategy@site` bot kinds there (site-aware starting, as the web opponents play).
  Add `"corporations": ["CEC", "KDY", "CSC", "KTG"], "planet_pair_bonus": {},
  "facility_rules": false, "fleet_limit": 4, "death_star_stage_values": [40, 50, 60, 70]`
  (`FLEET_CONFIG`) to compare with the fleet rules of 2026-10-26; the same corporations and bonus
  with `"death_star_rules": false, "facility_rules": false` (`CLASSIC_CONFIG`'s rules; facilities
  need the Death Star rules) to compare with the rules before 2026-10-26, and
  `"map_file": "map-127.json"` for the board before the east edge was cut (also 2026-10-26).
  Games with `death_star_rules` on get `ds.*` row fields from a move
  observer (`src/bby18/death_star_metrics.py`, no log parsing); `bby18 death-star-report --rows
  rows.jsonl` compares variants on the clock, fleets, bankruptcies, withholds and contracts
  (`--bot` keeps one bot mix). Every row also counts network actions (total and late) and planets
  touched; games with `facility_rules` on add `fac.*` fields
  (`src/bby18/facility_metrics.py`), which the report prints as a facilities block. Bots price
  planet exits in their routes in `src/bby18/bots/routing.py`.
- Web opponents: named characters in `src/bby18/bots/roster.py`, each a stable strategy started
  by the Death Star site (`roster_policy`, bot kind `strategy@site`) with a per-difficulty
  `noise` from `BOT_NOISE` in `config.py`. Recalibrate with `docs/sweeps/difficulty-2026-10-28`
  specs (script in `docs/sweeps/difficulty-2026-10-25`, reference `builder@site`) when the rules
  or a strategy change.
- Lane drawing on the web map: route and trace geometry in `web/src/lanes.ts`; the order of
  corporation traces across each border and each corporation's fork stem at junctions
  (crossings counted per hex, then drift, then sharp bends, then corporation order, packed
  around the lane's centre) is solved for the whole map in `web/src/laneOrder.ts`. Junctions
  draw as forks of ordinary bends, no disks; a corporation's trace reaches only the exits where
  it carries on (no spurs into hexes it doesn't serve).
- Rule enforcement: `src/bby18/game.py` and `src/bby18/network.py`. Drivers and bots decide what
  to do; these modules decide whether it is legal and apply the consequences.
- Death Star rules (`death_star_rules`, the default since 2026-10-26) with facilities and planet
  exits in place of fleets (`facility_rules`, the default since 2026-10-27, limit 3, contracts
  50-80; the web app serves only these): site placement, track state and fleet-price helpers in
  `src/bby18/death_star.py`; enforcement in `game.py` and, for planet exits, `network.py`; the
  fleet (facility) phase in `session.py`; the API's state block `facilities` in
  `src/bby18/api/serialize.py` and `web/src/facilities.ts`. Tests of the fleet rules use
  `FLEET_CONFIG` (API tests monkeypatch the served config, as in `tests/test_api_facilities.py`),
  tests of the rules before the Death Star `CLASSIC_CONFIG`; with those switches off, games must
  stay bit-identical (`tests/test_death_star.py` pins full-game log hashes of `CLASSIC_CONFIG`
  and `FLEET_CONFIG` games).

## Conventions

- Planets are hubs: no charting, no service cubes. Under the facility rules a planet has one
  exit plus one per facility, claimed by the lanes charted toward it; with them off every exit
  is open. See `network.py`.
- Hex coordinates are axial `(q, r)`, pointy-top, matching `docs/design/hex-map-design.md`.
- Bots must only choose from the legal action lists the engine provides.
- Keep the game end condition isolated in `Game.is_over`: the station's launch or the backstop
  round under the Death Star rules, the fixed round count under `CLASSIC_CONFIG`.
