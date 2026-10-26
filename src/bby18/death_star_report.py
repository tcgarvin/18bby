"""A plain-text summary of sweep rows for comparing the Death Star rules with the current ones.

It reads only row fields: the ``ds.*`` fields written by ``bby18.death_star_metrics`` for games
with the rules on, and a few fields every row has (``rounds_played``, ``shares_sold``, the
per-corporation dividend counts). Clock values are explained in ``bby18.death_star_metrics``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from statistics import mean, median
from typing import Any

from bby18.death_star import stage_name
from bby18.death_star_metrics import ROW_PREFIX
from bby18.playtest import seat_kinds

Row = dict[str, Any]

_CORP_PREFIX = f"{ROW_PREFIX}corp."


def death_star_report(rows: Iterable[Row]) -> str:
    """One block per variant, in name order."""
    by_variant: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        by_variant[str(row["variant"])].append(row)
    if not by_variant:
        raise ValueError("No rows to report on")
    return "\n\n".join(variant_report(name, by_variant[name]) for name in sorted(by_variant))


def variant_report(name: str, rows: Sequence[Row]) -> str:
    """The report block for one variant's rows."""
    missing = [r for r in rows if "rounds_played" not in r]
    if missing:
        raise ValueError(
            f"{len(missing)} rows of variant {name!r} have no rounds_played; "
            "they come from an older sweep, so re-run it"
        )
    rules_on = [r for r in rows if f"{ROW_PREFIX}launched" in r]
    if rules_on and len(rules_on) != len(rows):
        raise ValueError(f"Variant {name!r} mixes games with the Death Star rules on and off")
    state = "on" if rules_on else "off"
    rounds = [int(r["rounds_played"]) for r in rows]
    lines = [
        f"variant {name}: {len(rows)} games, Death Star rules {state}",
        f"  rounds played: mean {mean(rounds):.2f}, median {median(rounds):g}, "
        f"range {min(rounds)}-{max(rounds)}",
        f"  withheld operating turns (forced ones included): "
        f"{_percent(_corp_sum(rows, 'withholds'), _corp_sum(rows, 'operating_turns'))}",
        f"  shares sold per stock round after the first: "
        f"{_ratio(sum(int(r['shares_sold']) for r in rows), sum(n - 1 for n in rounds))}",
    ]
    if rules_on:
        lines += _death_star_lines(rows)
    return "\n".join(lines)


def _death_star_lines(rows: Sequence[Row]) -> list[str]:
    n = len(rows)
    p = ROW_PREFIX
    launched = sum(1 for r in rows if r[f"{p}launched"])
    lines = [
        f"  ended by the station launching: {100 * launched / n:.0f}% "
        f"(backstop {100 * (n - launched) / n:.0f}%)",
        "  stage fills (clock: OR r.i = k(r-1)+i, SR r = k(r-1)+0.5; k = 2 by default):",
    ]
    for index in range(1, _stage_count(rows) + 1):
        times = [float(r[f"{p}stage{index}.filled_at"]) for r in rows]
        filled = [t for t in times if t > 0]
        timing = (
            f", at mean {mean(filled):.1f}, median {median(filled):g}, "
            f"range {min(filled):g}-{max(filled):g}"
            if filled
            else ""
        )
        lines.append(
            f"    {stage_name(index - 1):<26} filled in {100 * len(filled) / n:3.0f}% of games"
            + timing
        )
    lines.append(
        f"  cubes per game: contracts {_mean_of(rows, 'contract_cubes'):.1f}, "
        f"Empire {_mean_of(rows, 'empire_cubes'):.1f}"
    )
    lines += _fleet_lines(rows)
    lines += _bankruptcy_lines(rows)
    lines += [
        "  withheld dividend choices (positive revenue only): "
        + _near_and_elsewhere(
            rows, "withholds", "dividend_choices", "near_seizure", "near a seizure", _percent
        ),
        "  shares sold per stock round (after the first): "
        + _near_and_elsewhere(
            rows,
            "shares_sold",
            "sale_rounds",
            "before_stage",
            "before a seizure or site move",
            _ratio,
        ),
        "  price change per corporation between operating-round ends: across the site move "
        + _ratio(
            _sum_of(rows, "site_move_price_delta"),
            _sum_of(rows, "site_move_price_corps"),
            signed=True,
        )
        + ", all rounds "
        + _ratio(_sum_of(rows, "or_price_delta"), _sum_of(rows, "or_price_corps"), signed=True),
    ]
    operated = _operated_corps(rows)
    revenue = _sum_of(rows, "revenue_total")
    contract_share = _sum_of(rows, "contract_revenue") / revenue if revenue else 0.0
    pairs = _operated_sum(rows, operated, "contract_pairs") / len(operated) if operated else 0.0
    lines.append(
        f"  contract revenue: {100 * contract_share:.1f}% of all revenue; contract pairs per "
        f"corporation that operated {pairs:.2f}"
    )
    return lines


def _near_and_elsewhere(
    rows: Sequence[Row],
    part: str,
    whole: str,
    suffix: str,
    label: str,
    show: Callable[[float, float], str],
) -> str:
    """``part / whole`` over the rounds the ``<field>_<suffix>`` fields count, and over the
    rest."""
    near_part, near_whole = _sum_of(rows, f"{part}_{suffix}"), _sum_of(rows, f"{whole}_{suffix}")
    elsewhere = show(_sum_of(rows, part) - near_part, _sum_of(rows, whole) - near_whole)
    return f"{label} {show(near_part, near_whole)}, elsewhere {elsewhere}"


def _fleet_lines(rows: Sequence[Row]) -> list[str]:
    operated = _operated_corps(rows)

    def per_corp(name: str) -> float:
        return _operated_sum(rows, operated, name) / len(operated) if operated else 0.0

    tiers = Counter(int(r[f"{ROW_PREFIX}final_fleet_tier"]) for r in rows)
    tier_text = ", ".join(f"tier {t} {100 * c / len(rows):.0f}%" for t, c in sorted(tiers.items()))
    owned_by_round: dict[int, list[float]] = defaultdict(list)
    prefix = f"{ROW_PREFIX}fleets_end_round."
    for r in rows:
        for key, value in r.items():
            if key.startswith(prefix):
                owned_by_round[int(key[len(prefix) :])].append(float(value))
    owned = " ".join(f"R{k} {mean(v):.1f}" for k, v in sorted(owned_by_round.items()))
    return [
        f"  fleets per corporation that operated ({len(operated)}): bought "
        f"{per_corp('fleets_bought'):.2f}, spent {per_corp('fleet_spend'):.0f}, seized "
        f"{per_corp('fleets_seized'):.2f}, left at the end {per_corp('final_fleets'):.2f}",
        f"  fleets sold per game {_mean_of(rows, 'fleets_sold'):.1f}; next fleet's tier at the "
        f"end: {tier_text}",
        f"  fleets owned at the end of each round (games that reached it): {owned}",
    ]


def _bankruptcy_lines(rows: Sequence[Row]) -> list[str]:
    n = len(rows)
    closures = [closure for r in rows for closure in _closures(r)]
    with_one = sum(1 for r in rows if int(r[f"{ROW_PREFIX}bankruptcies"]) > 0)
    by_round = Counter(round_number for round_number, _, _ in closures)
    by_corp = Counter(corp_id for _, corp_id, _ in closures)
    by_kind = Counter(kind for _, _, kind in closures)
    seats: Counter[str] = Counter()
    for r in rows:
        seats.update(seat_kinds(str(r["bot"]), int(r["player_count"])))
    lines = [
        f"  bankruptcies per game {len(closures) / n:.2f} (games with one: "
        f"{100 * with_one / n:.0f}%)"
        + (
            "; by round "
            + ", ".join(f"R{k} {v}" for k, v in sorted(by_round.items()))
            + "; by corporation "
            + ", ".join(f"{k} {v}" for k, v in sorted(by_corp.items()))
            if closures
            else ""
        ),
    ]
    if closures:
        lines.append("  bankruptcies by the president's strategy (count, per 100 seats played):")
        for kind in sorted(seats, key=lambda k: (-by_kind[k] / seats[k], k)):
            lines.append(
                f"    {kind:<16} {by_kind[kind]:4d} {100 * by_kind[kind] / seats[kind]:6.1f}"
            )
    return lines


def _closures(row: Row) -> list[tuple[int, str, str]]:
    """``(round, corporation, president's strategy)`` for each corporation closed in ``row``."""
    kinds = seat_kinds(str(row["bot"]), int(row["player_count"]))
    found = []
    for corp_id in _corp_ids(row):
        if not row[f"{_CORP_PREFIX}{corp_id}.closed"]:
            continue
        seat = str(row[f"{_CORP_PREFIX}{corp_id}.closed_president"])
        kind = kinds[int(seat.removeprefix("P")) - 1]
        found.append((int(row[f"{_CORP_PREFIX}{corp_id}.closed_round"]), corp_id, kind))
    return found


def _corp_ids(row: Row) -> list[str]:
    return sorted(
        {k[len(_CORP_PREFIX) :].split(".", 1)[0] for k in row if k.startswith(_CORP_PREFIX)}
    )


def _operated_corps(rows: Sequence[Row]) -> list[tuple[int, str]]:
    """``(row index, corporation)`` for every corporation that floated, closed or not."""
    return [
        (i, corp_id)
        for i, r in enumerate(rows)
        for corp_id in _corp_ids(r)
        if r.get(f"corp.{corp_id}.floated") or r[f"{_CORP_PREFIX}{corp_id}.closed"]
    ]


def _operated_sum(rows: Sequence[Row], operated: list[tuple[int, str]], name: str) -> float:
    return sum(float(rows[i][f"{_CORP_PREFIX}{corp_id}.{name}"]) for i, corp_id in operated)


def _stage_count(rows: Sequence[Row]) -> int:
    return max(
        sum(1 for k in r if k.startswith(f"{ROW_PREFIX}stage") and k.endswith(".filled_at"))
        for r in rows
    )


def _corp_sum(rows: Sequence[Row], name: str) -> float:
    """``corp.<id>.<name>`` summed over every corporation and row."""
    suffix = f".{name}"
    return sum(
        float(v) for r in rows for k, v in r.items() if k.startswith("corp.") and k.endswith(suffix)
    )


def _sum_of(rows: Sequence[Row], name: str) -> float:
    return sum(float(r[f"{ROW_PREFIX}{name}"]) for r in rows)


def _mean_of(rows: Sequence[Row], name: str) -> float:
    return _sum_of(rows, name) / len(rows)


def _percent(part: float, whole: float) -> str:
    if whole == 0:
        return "n/a (n=0)"
    return f"{100 * part / whole:.1f}% (n={whole:g})"


def _ratio(total: float, count: float, digits: int = 2, signed: bool = False) -> str:
    if count == 0:
        return "n/a (n=0)"
    sign = "+" if signed else ""
    return f"{total / count:{sign}.{digits}f} (n={count:g})"
