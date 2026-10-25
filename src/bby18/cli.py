"""Command-line playtest harness."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from bby18.config import DEFAULT_CONFIG
from bby18.playtest import BOT_KINDS, play_many, play_one, seat_kinds
from bby18.terrain_report import terrain_report
from bby18.sweep import SweepError, load_spec, read_rows, row_keys, run_sweep, summarize

SWEEP_EPILOG = """\
spec.json:
  {"variants": {"baseline": {}, "cheap_charts": {"chart_cost": 10}},
   "grid": {"chart_cost": [10, 20, 30], "typed_pair_value": [25, 30, 35]},
   "seeds": [1, 32], "players": [2, 3, 4], "bots": ["greedy"]}

"variants" maps a name to GameConfig field overrides. "grid" adds the Cartesian product of the
listed values, named like "chart_cost=10|typed_pair_value=30". Tuple and set fields take JSON
lists; starting_cash_by_player_count takes an object. "seeds" is [start, count].
"bots" entries are bot kinds (see playtest --help) or "mix:kind1,kind2,..." strings, which
assign kinds to seats round-robin from seat 1.
"""

BOTS_HELP = (
    f"one of {', '.join(BOT_KINDS)}, or mix:kind1,kind2,... to assign kinds round-robin by seat"
)


def bot_kind(value: str) -> str:
    """argparse type for --bots: a known kind or a mix: string."""
    try:
        seat_kinds(value, 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return value


def main() -> None:
    parser = argparse.ArgumentParser(prog="bby18", description="18BBY playtest harness")
    sub = parser.add_subparsers(dest="command", required=True)

    p_batch = sub.add_parser("playtest", help="run many bot games and print aggregate stats")
    p_batch.add_argument("--games", type=int, default=20)
    p_batch.add_argument("--players", type=int, default=3)
    p_batch.add_argument("--bots", type=bot_kind, default="greedy", help=BOTS_HELP)
    p_batch.add_argument("--seed", type=int, default=1)

    p_replay = sub.add_parser("replay", help="play one game and print its full log")
    p_replay.add_argument("--players", type=int, default=3)
    p_replay.add_argument("--bots", type=bot_kind, default="greedy", help=BOTS_HELP)
    p_replay.add_argument("--seed", type=int, default=1)

    p_terrain = sub.add_parser(
        "terrain-report",
        help="measure, from the map alone, how terrain changes the cost of linking planets",
    )
    p_terrain.add_argument("--seeds", type=int, default=200)

    p_sweep = sub.add_parser(
        "sweep",
        help="run a parameter sweep in parallel and write one JSON row per game",
        epilog=SWEEP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_sweep.add_argument("--spec", type=Path, required=True)
    p_sweep.add_argument("--out", type=Path, required=True, help="results JSONL, one row per game")
    p_sweep.add_argument("--summary", type=Path, help="write grouped summary JSON here")
    p_sweep.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    mode = p_sweep.add_mutually_exclusive_group()
    mode.add_argument(
        "--resume", action="store_true", help="keep existing rows in --out; play only the rest"
    )
    mode.add_argument("--overwrite", action="store_true", help="replace an existing --out")

    p_serve = sub.add_parser("serve", help="run the HTTP API for the web frontend")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")

    sub.add_parser(
        "migrate", help="create or update the saved-games tables in the database at DATABASE_URL"
    )

    args = parser.parse_args()
    if args.command == "migrate":
        sys.exit(migrate_command())
    if args.command == "serve":
        import uvicorn

        # Local play by default: games in memory, one local user, no sign-in.
        os.environ.setdefault("BBY18_MODE", "local")
        uvicorn.run("bby18.api.main:app", port=args.port, reload=args.reload)
        return
    if args.command == "sweep":
        sys.exit(sweep_command(args))
    if args.command == "terrain-report":
        report = terrain_report(range(1, args.seeds + 1), DEFAULT_CONFIG)
        print(json.dumps(report, indent=1))
        return
    if args.command == "playtest":
        print(play_many(args.games, args.players, args.bots, DEFAULT_CONFIG, args.seed).report())
    elif args.command == "replay":
        game, summary = play_one(args.seed, args.players, args.bots, DEFAULT_CONFIG)
        for entry in game.log:
            print(entry)
        print()
        for p in game.players:
            print(f"{p.name}: cash {p.cash}, worth {game.player_worth(p)}, shares {p.shares}")
        for c in game.operating_order():
            pairs = ", ".join(str(pair) for pair in game.revenue(c).pairs)
            print(
                f"{c.id}: price {game.price(c)}, treasury {c.treasury}, revenue {c.last_revenue}: {pairs}"
            )
        print(f"winner: {summary.winner}")


def migrate_command() -> int:
    from bby18.api.store import PostgresStore, StoreError

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("Set DATABASE_URL to the database to migrate.", file=sys.stderr)
        return 2
    try:
        PostgresStore(database_url).migrate()
    except StoreError as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1
    print("Schema is up to date.")
    return 0


def sweep_command(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec)
    out_path: Path = args.out
    existing: list[dict[str, object]] = []
    if out_path.exists() and out_path.stat().st_size > 0:
        if args.resume:
            existing = read_rows(out_path)
            # Rewrite without any truncated last line so appended rows start on a fresh line.
            tmp_path = out_path.with_name(out_path.name + ".tmp")
            tmp_path.write_text("".join(json.dumps(r) + "\n" for r in existing), encoding="utf-8")
            tmp_path.replace(out_path)
        elif not args.overwrite:
            print(f"{out_path} exists; pass --resume or --overwrite", file=sys.stderr)
            return 2
    mode = "a" if args.resume else "w"
    status = 0
    with out_path.open(mode, encoding="utf-8") as out:
        try:
            rows = run_sweep(
                spec.variants,
                spec.seeds,
                spec.player_counts,
                spec.bot_kinds,
                args.workers,
                out=out,
                skip=row_keys(existing),
                progress=sys.stderr,
            )
        except SweepError as exc:
            print(exc, file=sys.stderr)
            errors_path = out_path.with_name(out_path.name + ".errors.jsonl")
            with errors_path.open("w", encoding="utf-8") as errors:
                for failure in exc.failures:
                    errors.write(json.dumps(failure) + "\n")
            print(f"failures written to {errors_path}", file=sys.stderr)
            rows = exc.rows
            status = 1
    if args.summary is not None:
        summary = summarize(existing + rows)
        args.summary.write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    return status


if __name__ == "__main__":
    main()
