"""Summarize a difficulty check sweep: the reference player's mean share against each strategy.

uv run python docs/sweeps/difficulty-2026-10-29/check.py rows.jsonl [builder@site]
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

from bby18.playtest import NOISE_SEPARATOR, START_SEPARATOR, seat_kinds
from bby18.sweep import read_rows

REFERENCE = "builder@site"


def main() -> None:
    rows = read_rows(Path(sys.argv[1]))
    reference = sys.argv[2] if len(sys.argv) > 2 else REFERENCE
    shares: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        kinds = seat_kinds(str(row["bot"]), 3)
        worth = [float(row[f"worth.P{i + 1}"]) for i in range(3)]  # type: ignore[arg-type]
        seat = kinds.index(reference)
        opponent = next(k for k in kinds if k != reference)
        strategy = opponent.partition(NOISE_SEPARATOR)[0].partition(START_SEPARATOR)[0]
        shares[strategy].append(worth[seat] / sum(worth))
    print(f"{'strategy':<15} share  s.e.  games")
    for strategy, values in sorted(shares.items(), key=lambda kv: mean(kv[1])):
        error = stdev(values) / len(values) ** 0.5
        print(f"{strategy:<15} {100 * mean(values):5.1f} {100 * error:5.1f} {len(values):6d}")
    every = [v for values in shares.values() for v in values]
    print(f"{'overall':<15} {100 * mean(every):5.1f}       {len(every):6d}")


if __name__ == "__main__":
    main()
