"""Parameter sweeps: many config variants x seeds x player counts x bots, run in parallel.

Each game becomes one flat JSON row. Rows are appended to a JSONL file as games finish, so an
interrupted sweep keeps its results and can be resumed.
"""

from __future__ import annotations

import itertools
import json
import sys
import time
import traceback
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from dataclasses import dataclass, fields, replace
from pathlib import Path
from statistics import mean, pstdev
from typing import IO, Any, get_args, get_origin, get_type_hints

from bby18.bots.stable import STABLE
from bby18.config import (
    UNLIMITED,
    DEFAULT_CONFIG,
    CorporationSpec,
    FleetTier,
    GameConfig,
    Unlimited,
)
from bby18.game import Game
from bby18.playtest import play_one, seat_kinds
from bby18.tournament import tournament_bots

META_KEYS = ("variant", "overrides", "player_count", "bot", "seed")
"""Row keys that identify a game rather than measure it."""

Row = dict[str, Any]

_FIELD_TYPES: dict[str, Any] = get_type_hints(GameConfig)
_FIELD_NAMES = frozenset(f.name for f in fields(GameConfig))


class SweepError(Exception):
    """Raised after a sweep finishes when some games failed. Carries the successful rows."""

    def __init__(self, failures: list[Row], rows: list[Row]) -> None:
        first = failures[0]
        super().__init__(
            f"{len(failures)} game(s) failed; first: variant={first['variant']} "
            f"players={first['player_count']} bot={first['bot']} seed={first['seed']}\n"
            f"{first['error']}"
        )
        self.failures = failures
        self.rows = rows


# --- building variants ---------------------------------------------------------------------


def coerce_field(name: str, value: Any) -> Any:
    """Convert a JSON-style value (lists, string-keyed objects) to the type of a config field."""
    if name not in _FIELD_NAMES:
        raise ValueError(f"{name!r} is not a GameConfig field")
    try:
        return _coerce(_FIELD_TYPES[name], value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Bad value for {name}: {value!r} ({exc})") from exc


def _coerce(hint: Any, value: Any) -> Any:
    origin = get_origin(hint)
    args = get_args(hint)
    if hint is bool:
        if not isinstance(value, bool):
            raise TypeError(f"expected a boolean, got {type(value).__name__}")
        return value
    if hint is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"expected a number, got {type(value).__name__}")
        return float(value)
    if hint is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"expected an int, got {type(value).__name__}")
        return value
    if hint is str:
        if not isinstance(value, str):
            raise TypeError(f"expected a string, got {type(value).__name__}")
        return value
    if hint is CorporationSpec:
        if isinstance(value, CorporationSpec):
            return value
        if isinstance(value, Mapping):
            return CorporationSpec(**value)
        return CorporationSpec(*value)
    if hint is FleetTier:
        return _coerce_fleet_tier(value)
    if origin is tuple:
        if isinstance(value, (str, Mapping)):
            raise TypeError("expected a list")
        return tuple(_coerce(args[0], v) for v in value)
    if origin is frozenset:
        if isinstance(value, (str, Mapping)):
            raise TypeError("expected a list")
        return frozenset(_coerce(args[0], v) for v in value)
    if origin is dict:
        if not isinstance(value, Mapping):
            raise TypeError("expected an object")
        key_type, value_type = args
        return {
            _coerce(key_type, int(k) if key_type is int and isinstance(k, str) else k): _coerce(
                value_type, v
            )
            for k, v in value.items()
        }
    raise TypeError(f"unsupported field type {hint}")


def _coerce_fleet_tier(value: Any) -> FleetTier:
    """A fleet tier from ``[count, price]`` or ``{"count": ..., "price": ...}``; the count may be
    ``"unlimited"``."""
    if isinstance(value, FleetTier):
        return value
    if isinstance(value, Mapping):
        count, price = value["count"], value["price"]
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        count, price = value
    else:
        raise TypeError("expected a fleet tier as [count, price]")
    tier_count = UNLIMITED if count == UNLIMITED.value else _coerce(int, count)
    return FleetTier(tier_count, _coerce(int, price))


def variant(config: GameConfig, **overrides: Any) -> GameConfig:
    """``config`` with some fields replaced. Unknown field names raise ``ValueError``.

    Values may be JSON-style (lists for tuples and sets, objects for dicts).
    """
    unknown = sorted(set(overrides) - _FIELD_NAMES)
    if unknown:
        raise ValueError(f"Not GameConfig fields: {', '.join(unknown)}")
    coerced = {name: coerce_field(name, value) for name, value in overrides.items()}
    return replace(config, **coerced)


def to_jsonable(value: Any) -> Any:
    """A JSON-friendly form of a config value, with sets sorted for stable output."""
    if isinstance(value, CorporationSpec):
        return {"id": value.id, "name": value.name, "homeworld": value.homeworld}
    if isinstance(value, FleetTier):
        count = value.count.value if isinstance(value.count, Unlimited) else value.count
        return [count, value.price]
    if isinstance(value, (tuple, list)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, frozenset):
        return sorted((to_jsonable(v) for v in value), key=json.dumps)
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    return value


def config_overrides(config: GameConfig, base: GameConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    """The fields of ``config`` that differ from ``base``, JSON-ready."""
    return {
        f.name: to_jsonable(getattr(config, f.name))
        for f in fields(GameConfig)
        if getattr(config, f.name) != getattr(base, f.name)
    }


def grid_variants(base: GameConfig, grid: Mapping[str, list[Any]]) -> dict[str, GameConfig]:
    """The Cartesian product of ``grid`` values, named like ``chart_cost=10|typed_pair_value=30``."""
    if not grid:
        raise ValueError("A grid needs at least one field")
    names = list(grid)
    for name in names:
        values = grid[name]
        if not isinstance(values, list) or not values:
            raise ValueError(f"Grid field {name!r} needs a non-empty list of values")
    variants: dict[str, GameConfig] = {}
    for combo in itertools.product(*(grid[n] for n in names)):
        label = "|".join(
            f"{n}={json.dumps(v, separators=(',', ':'))}" for n, v in zip(names, combo)
        )
        variants[label] = variant(base, **dict(zip(names, combo)))
    return variants


# --- specs ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class SweepSpec:
    variants: dict[str, GameConfig]
    seeds: range
    player_counts: list[int]
    bot_kinds: list[str]


def parse_spec(data: Mapping[str, Any]) -> SweepSpec:
    """Validate and expand a sweep spec (see ``bby18 sweep --help``)."""
    allowed = {"variants", "grid", "seeds", "players", "bots", "tournament"}
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(f"Unknown spec keys: {', '.join(unknown)}")
    if "tournament" in data and "bots" in data:
        raise ValueError("Give 'bots' or 'tournament', not both")
    variants: dict[str, GameConfig] = {}
    for name, overrides in data.get("variants", {}).items():
        if not isinstance(overrides, Mapping):
            raise ValueError(f"Variant {name!r} must be an object of field overrides")
        variants[name] = variant(DEFAULT_CONFIG, **overrides)
    if "grid" in data:
        for name, config in grid_variants(DEFAULT_CONFIG, data["grid"]).items():
            if name in variants:
                raise ValueError(f"Grid variant {name!r} clashes with a named variant")
            variants[name] = config
    if not variants:
        raise ValueError("The spec defines no variants; add 'variants' or 'grid'")
    seeds = data.get("seeds")
    if not (isinstance(seeds, list) and len(seeds) == 2 and all(isinstance(s, int) for s in seeds)):
        raise ValueError("'seeds' must be [start, count]")
    players = data.get("players", [3])
    if not players or not all(isinstance(p, int) for p in players):
        raise ValueError("'players' must be a non-empty list of player counts")
    if "tournament" in data:
        bots = _tournament_bots(data["tournament"], players)
    else:
        bots = data.get("bots", ["greedy"])
    if not bots or not all(isinstance(b, str) for b in bots):
        raise ValueError("'bots' must be a non-empty list of bot kinds")
    return SweepSpec(variants, range(seeds[0], seeds[0] + seeds[1]), list(players), list(bots))


def _tournament_bots(strategies: Any, players: list[int]) -> list[str]:
    """Every seating of a strategy tournament. Seatings fill every seat, so one player count."""
    if len(players) != 1:
        raise ValueError("A tournament spec takes exactly one player count")
    if strategies == "stable":
        strategies = list(STABLE)
    if not (
        isinstance(strategies, list) and strategies and all(isinstance(s, str) for s in strategies)
    ):
        raise ValueError("'tournament' must be \"stable\" or a non-empty list of bot kinds")
    return tournament_bots(strategies, players[0])


def load_spec(path: Path) -> SweepSpec:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return parse_spec(data)


# --- running -------------------------------------------------------------------------------


@dataclass(frozen=True)
class GameTask:
    variant: str
    config: GameConfig
    seed: int
    player_count: int
    bot: str

    @property
    def key(self) -> tuple[str, int, str, int]:
        return (self.variant, self.player_count, self.bot, self.seed)


def run_task(task: GameTask) -> Row:
    """Play one game and return its row. Runs in a worker process."""
    start = time.perf_counter()
    _, summary = play_one(task.seed, task.player_count, task.bot, task.config)
    row: Row = {
        "variant": task.variant,
        "overrides": config_overrides(task.config),
        "player_count": task.player_count,
        "bot": task.bot,
        "seed": task.seed,
    }
    row.update(summary.to_row())
    row["seconds"] = time.perf_counter() - start
    return row


def _run_task_safely(task: GameTask) -> tuple[Row, str]:
    """``run_task``, turning a failure into a traceback string so one bad game does not
    abandon the rest of the sweep. The caller reports every failure."""
    try:
        return run_task(task), ""
    except Exception:
        return {}, traceback.format_exc()


def build_tasks(
    variants: Mapping[str, GameConfig],
    seeds: Iterable[int],
    player_counts: Iterable[int],
    bot_kinds: Iterable[str],
) -> list[GameTask]:
    seed_list = list(seeds)
    return [
        GameTask(name, config, seed, players, bot)
        for name, config in variants.items()
        for players in player_counts
        for bot in bot_kinds
        for seed in seed_list
    ]


def validate_tasks(tasks: list[GameTask]) -> None:
    """Fail fast, before any worker starts, on configs or bots that cannot make a game."""
    checked: set[tuple[str, int]] = set()
    for task in tasks:
        seat_kinds(task.bot, task.player_count)
        if (task.variant, task.player_count) in checked:
            continue
        try:
            Game.new([f"Player {i + 1}" for i in range(task.player_count)], task.config)
        except (ValueError, KeyError) as exc:
            raise ValueError(
                f"Variant {task.variant!r} cannot start a {task.player_count}-player game: {exc}"
            ) from exc
        checked.add((task.variant, task.player_count))


def run_sweep(
    variants: Mapping[str, GameConfig],
    seeds: Iterable[int],
    player_counts: list[int],
    bot_kinds: list[str],
    workers: int,
    out: IO[str] | None = None,
    skip: frozenset[tuple[str, int, str, int]] = frozenset(),
    progress: IO[str] | None = None,
) -> list[Row]:
    """Play every (variant, player count, bot, seed) game and return one row per game.

    ``out`` receives each row as a JSON line the moment its game finishes. Games whose
    ``(variant, player_count, bot, seed)`` key is in ``skip`` are not played (for resuming).
    ``workers`` of 1 plays in this process. Rows come back sorted by that key. If any game
    raises, the rest still run and a ``SweepError`` is raised at the end.
    """
    if workers < 1:
        raise ValueError("workers must be at least 1")
    tasks = [t for t in build_tasks(variants, seeds, player_counts, bot_kinds) if t.key not in skip]
    validate_tasks(tasks)
    rows: list[Row] = []
    failures: list[Row] = []
    reporter = _Progress(len(tasks), progress)
    for task, (row, error) in _execute(tasks, workers):
        if error:
            failures.append(
                {
                    "variant": task.variant,
                    "player_count": task.player_count,
                    "bot": task.bot,
                    "seed": task.seed,
                    "error": error,
                }
            )
        else:
            rows.append(row)
            if out is not None:
                out.write(json.dumps(row) + "\n")
                out.flush()
        reporter.update(task, failed=bool(error))
    reporter.finish()
    rows.sort(key=_row_key)
    if failures:
        raise SweepError(failures, rows)
    return rows


def _execute(tasks: list[GameTask], workers: int) -> Iterator[tuple[GameTask, tuple[Row, str]]]:
    if workers == 1:
        for task in tasks:
            yield task, _run_task_safely(task)
        return
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures: dict[Future[tuple[Row, str]], GameTask] = {
            pool.submit(_run_task_safely, task): task for task in tasks
        }
        for future in as_completed(futures):
            yield futures[future], future.result()


def _row_key(row: Row) -> tuple[str, int, str, int]:
    return (str(row["variant"]), int(row["player_count"]), str(row["bot"]), int(row["seed"]))


class _Progress:
    """Throttled progress lines on stderr (or any stream)."""

    INTERVAL_SECONDS = 2.0

    def __init__(self, total: int, stream: IO[str] | None) -> None:
        self.total = total
        self.stream = stream
        self.done = 0
        self.failed = 0
        self.start = time.perf_counter()
        self.last = 0.0

    def update(self, task: GameTask, failed: bool) -> None:
        self.done += 1
        self.failed += int(failed)
        now = time.perf_counter()
        if self.stream is None or (now - self.last < self.INTERVAL_SECONDS):
            return
        self.last = now
        elapsed = now - self.start
        rate = self.done / elapsed
        eta = (self.total - self.done) / rate
        self.stream.write(
            f"[{self.done}/{self.total}] {elapsed:.0f}s elapsed, {rate:.2f} games/s, "
            f"eta {eta:.0f}s, failed {self.failed} (last: {task.variant} "
            f"p{task.player_count} {task.bot} seed {task.seed})\n"
        )
        self.stream.flush()

    def finish(self) -> None:
        if self.stream is None:
            return
        elapsed = time.perf_counter() - self.start
        self.stream.write(f"done: {self.done} games in {elapsed:.1f}s, failed {self.failed}\n")
        self.stream.flush()


def read_rows(path: Path) -> list[Row]:
    """Rows from a results JSONL file. A truncated final line (from an interrupted write) is
    dropped; a malformed line anywhere else is an error."""
    lines = path.read_text(encoding="utf-8").splitlines()
    rows: list[Row] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            if number == len(lines):
                print(f"warning: dropping truncated last line of {path}", file=sys.stderr)
                break
            raise ValueError(f"{path}:{number} is not valid JSON") from exc
    return rows


def row_keys(rows: Iterable[Row]) -> frozenset[tuple[str, int, str, int]]:
    return frozenset(_row_key(r) for r in rows)


# --- summarizing ---------------------------------------------------------------------------


def summarize(rows: Iterable[Row]) -> list[Row]:
    """Group rows by (variant, player_count, bot) and aggregate every numeric metric.

    Each group has ``games``, ``win_rate`` by seat, ``float_rate`` by corporation, ``mean``
    and ``stdev`` of every numeric metric (booleans count as 0/1), and ``mean_when_floated``
    of each per-corporation metric over the games in which that corporation floated.
    """
    groups: dict[tuple[str, int, str], list[Row]] = defaultdict(list)
    for row in rows:
        groups[(str(row["variant"]), int(row["player_count"]), str(row["bot"]))].append(row)
    return [_summarize_group(key, groups[key]) for key in sorted(groups)]


def _summarize_group(key: tuple[str, int, str], rows: list[Row]) -> Row:
    name, players, bot = key
    n = len(rows)
    metric_names = sorted(
        {k for r in rows for k, v in r.items() if k not in META_KEYS and _is_number(v)}
    )
    means: dict[str, float] = {}
    stdevs: dict[str, float] = {}
    for metric in metric_names:
        values = [float(r[metric]) for r in rows if metric in r]
        means[metric] = mean(values)
        stdevs[metric] = pstdev(values)
    seats = sorted({k.split(".", 1)[1] for r in rows for k in r if k.startswith("worth.")})
    wins = {seat: sum(1 for r in rows if r["winner"] == seat) / n for seat in seats}
    corps = sorted({k.split(".")[1] for r in rows for k in r if k.startswith("corp.")})
    float_rate = {c: means.get(f"corp.{c}.floated", 0.0) for c in corps}
    return {
        "variant": name,
        "overrides": rows[0]["overrides"],
        "player_count": players,
        "bot": bot,
        "games": n,
        "win_rate": wins,
        "float_rate": float_rate,
        "mean": means,
        "stdev": stdevs,
        "mean_when_floated": _mean_when_floated(rows, corps),
    }


def _mean_when_floated(rows: list[Row], corps: list[str]) -> dict[str, float]:
    result: dict[str, float] = {}
    for corp in corps:
        prefix = f"corp.{corp}."
        floated = [r for r in rows if r.get(f"{prefix}floated")]
        if not floated:
            continue
        for metric in sorted(k for k in floated[0] if k.startswith(prefix)):
            if metric == f"{prefix}floated" or not _is_number(floated[0][metric]):
                continue
            result[metric] = mean(float(r[metric]) for r in floated)
    return result


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, bool))
