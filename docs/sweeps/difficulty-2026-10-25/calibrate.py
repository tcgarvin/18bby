"""Read a noise calibration sweep and suggest each strategy's noise for a target share.

The sweep seats one reference player (``builder``) with two copies of ``strategy~noise``, in all
three seat orders (a third argument names another reference kind, such as ``builder@site``).
For each strategy this prints the reference player's mean share at every
noise level and the lowest noise at which that share reaches the target, interpolating linearly
between levels. A strategy that never rises through the target gets the level closest to it.

    uv run python docs/sweeps/difficulty-2026-10-25/calibrate.py rows.jsonl 0.50 [builder@site]
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

from bby18.playtest import NOISE_SEPARATOR, START_SEPARATOR, seat_kinds
from bby18.sweep import read_rows

REFERENCE = "builder"
NEAR_TARGET = 0.01
"""How close to the target counts as on it, for a strategy that starts easier than the target."""


def reference_shares(
    rows: list[dict[str, object]], reference: str = REFERENCE
) -> dict[str, dict[float, list[float]]]:
    shares: dict[str, dict[float, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        kinds = seat_kinds(str(row["bot"]), 3)
        worth = [float(row[f"worth.P{i + 1}"]) for i in range(3)]  # type: ignore[arg-type]
        seat = kinds.index(reference)
        opponent = next(k for k in kinds if k != reference)
        named, _, level = opponent.partition(NOISE_SEPARATOR)
        strategy = named.partition(START_SEPARATOR)[0]
        shares[strategy][float(level)].append(worth[seat] / sum(worth))
    return shares


def noise_for(target: float, curve: dict[float, float]) -> float:
    """The lowest noise at which the curve rises through ``target``; if it never does (a
    strategy that noise makes harder, such as diversifier), the level closest to the target."""
    levels = sorted(curve)
    if curve[levels[0]] >= target:
        # Already easy enough without noise: the least noise that lands near the target.
        near = [lvl for lvl in levels if abs(curve[lvl] - target) <= NEAR_TARGET]
        return near[0] if near else min(levels, key=lambda lvl: abs(curve[lvl] - target))
    for low, high in zip(levels, levels[1:]):
        if curve[low] < target <= curve[high]:
            return round(low + (target - curve[low]) / (curve[high] - curve[low]) * (high - low), 2)
    return min(levels, key=lambda lvl: abs(curve[lvl] - target))


def main() -> None:
    rows = read_rows(Path(sys.argv[1]))
    target = float(sys.argv[2])
    shares = reference_shares(rows, sys.argv[3] if len(sys.argv) > 3 else REFERENCE)
    levels = sorted({lvl for curve in shares.values() for lvl in curve})
    print("reference share (%) by opponent noise; last column: noise for target", target)
    print(f"{'strategy':<15}" + "".join(f"{lvl:>6.1f}" for lvl in levels) + "   noise")
    suggestions: dict[str, float] = {}
    for strategy in sorted(shares, key=lambda s: mean(shares[s][0.0])):
        curve = {lvl: mean(v) for lvl, v in shares[strategy].items()}
        suggestions[strategy] = noise_for(target, curve)
        cells = "".join(f"{100 * curve[lvl]:6.1f}" for lvl in levels)
        print(f"{strategy:<15}{cells}   {suggestions[strategy]:.2f}")
    spread = max(stdev(v) / len(v) ** 0.5 for curve in shares.values() for v in curve.values())
    print(f"largest standard error of a cell: {100 * spread:.1f} points")
    print("BOT_NOISE entry:")
    print("{" + ", ".join(f'"{s}": {n}' for s, n in sorted(suggestions.items())) + "}")


if __name__ == "__main__":
    main()
