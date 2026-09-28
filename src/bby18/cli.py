"""Command-line playtest harness."""

from __future__ import annotations

import argparse

from bby18.config import DEFAULT_CONFIG
from bby18.playtest import play_many, play_one


def main() -> None:
    parser = argparse.ArgumentParser(prog="bby18", description="18BBY playtest harness")
    sub = parser.add_subparsers(dest="command", required=True)

    p_batch = sub.add_parser("playtest", help="run many bot games and print aggregate stats")
    p_batch.add_argument("--games", type=int, default=20)
    p_batch.add_argument("--players", type=int, default=3)
    p_batch.add_argument("--bots", choices=["greedy", "random"], default="greedy")
    p_batch.add_argument("--seed", type=int, default=1)

    p_replay = sub.add_parser("replay", help="play one game and print its full log")
    p_replay.add_argument("--players", type=int, default=3)
    p_replay.add_argument("--bots", choices=["greedy", "random"], default="greedy")
    p_replay.add_argument("--seed", type=int, default=1)

    args = parser.parse_args()
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


if __name__ == "__main__":
    main()
