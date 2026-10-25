"""Compare sweep variants: planet value, missed connections, choice indicators."""
import json, sys
from collections import defaultdict
from math import sqrt
from statistics import mean, pstdev

rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
BASE = sys.argv[2] if len(sys.argv) > 2 else "old"
groups = defaultdict(list)
for r in rows:
    groups[(r["bot"], r["player_count"], r["variant"])].append(r)

def ms(vals):
    vals = list(vals)
    return mean(vals), (pstdev(vals) / sqrt(len(vals)) if len(vals) > 1 else 0.0)

def fmt(v):
    m, se = v
    return f"{m:8.2f}±{se:4.2f}"

def per_corp_floated(rs, field):
    out = []
    for r in rs:
        for k, v in r.items():
            if k.startswith("corp.") and k.endswith(".floated") and v:
                c = k.split(".")[1]
                out.append(r[f"corp.{c}.{field}"])
    return out

planets = sorted({k.split(".")[1] for r in rows[:1] for k in r if k.startswith("planet.")})
variants = list(dict.fromkeys(r["variant"] for r in rows))
bots = sorted({r["bot"] for r in rows})
pcs = sorted({r["player_count"] for r in rows})

def gini(xs):
    xs = sorted(xs); n = len(xs); s = sum(xs)
    if s == 0: return 0.0
    return sum((2 * (i + 1) - n - 1) * x for i, x in enumerate(xs)) / (n * s)

def corp_revs(r):
    return [r[k] for k in r if k.startswith("corp.") and k.endswith(".revenue") and r[k.replace(".revenue", ".floated")]]

def spread(rs):
    return ms(pstdev(corp_revs(r)) for r in rs)

def planets_spread(rs):
    vals = [mean(per_corp_floated([r], "planets_reached")) for r in rs]
    return (pstdev(vals), 0.0)

METRICS = [
    ("mean_worth", lambda rs: ms(r["mean_worth"] for r in rs)),
    ("floated corps", lambda rs: ms(r["floated"] for r in rs)),
    ("corp revenue (final)", lambda rs: ms(per_corp_floated(rs, "revenue"))),
    ("corp planets reached", lambda rs: ms(per_corp_floated(rs, "planets_reached"))),
    ("planets reached by any (frac)", lambda rs: ms(r["planets_reached_fraction"] for r in rs)),
    ("near pairs linked (frac)", lambda rs: ms(r["near_pairs_linked"] / r["near_pairs"] for r in rs)),
    ("near pairs stranded (frac)", lambda rs: ms(r["near_pairs_stranded"] / r["near_pairs"] for r in rs)),
    ("corp unreached planets", lambda rs: ms(per_corp_floated(rs, "unreached_planets"))),
    ("corp cheap unreached (<150)", lambda rs: ms(per_corp_floated(rs, "cheap_unreached"))),
    ("corp next-planet cost", lambda rs: ms(per_corp_floated(rs, "next_planet_cost"))),
    ("corp charts", lambda rs: ms(per_corp_floated(rs, "charts"))),
    ("corp nebula charts", lambda rs: ms(per_corp_floated(rs, "nebula_charts"))),
    ("corp upgrades", lambda rs: ms(per_corp_floated(rs, "upgrades"))),
    ("corp services", lambda rs: ms(per_corp_floated(rs, "services"))),
    ("corp no-action turns", lambda rs: ms(per_corp_floated(rs, "no_network_actions"))),
    ("corp withholds", lambda rs: ms(per_corp_floated(rs, "withholds"))),
    ("corp final treasury", lambda rs: ms(per_corp_floated(rs, "treasury"))),
    ("within-game corp revenue sd", spread),
    ("between-game sd of planets/corp", planets_spread),
    ("tiles charted", lambda rs: ms(r["tiles_charted"] for r in rs)),
    ("junctions", lambda rs: ms(r["junctions"] for r in rs)),
    ("shared tiles", lambda rs: ms(r["shared_tiles"] for r in rs)),
    ("winner margin", lambda rs: ms(r["winner_margin"] for r in rs)),
    ("worth cv", lambda rs: ms(r["worth_cv"] for r in rs)),
]

def planet_vec(rs, field):
    return {p: mean(r[f"planet.{p}.{field}"] for r in rs) for p in planets}

for bot in bots:
    for pc in pcs:
        print(f"\n===== bot={bot} players={pc} (n per variant = {len(groups[(bot, pc, variants[0])])}) =====")
        vs = [v for v in variants if (bot, pc, v) in groups]
        print(f"{'metric':32s}" + "".join(f"{v:>16s}" for v in vs))
        for name, fn in METRICS:
            print(f"{name:32s}" + "".join(f"{fmt(fn(groups[(bot, pc, v)])):>16s}" for v in vs))
        # planet value inequality
        print(f"{'planet value gini':32s}" + "".join(f"{gini(list(planet_vec(groups[(bot,pc,v)],'value').values())):16.3f}" for v in vs))
        print(f"{'planet reach gini':32s}" + "".join(f"{gini(list(planet_vec(groups[(bot,pc,v)],'reached_by').values())):16.3f}" for v in vs))
        print(f"{'planet value total':32s}" + "".join(f"{sum(planet_vec(groups[(bot,pc,v)],'value').values()):16.1f}" for v in vs))
        # per-planet change vs base
        if (bot, pc, BASE) in groups:
            base_v = planet_vec(groups[(bot, pc, BASE)], "value")
            base_r = planet_vec(groups[(bot, pc, BASE)], "reached_by")
            for v in vs:
                if v == BASE: continue
                pv = planet_vec(groups[(bot, pc, v)], "value")
                pr = planet_vec(groups[(bot, pc, v)], "reached_by")
                dv = sorted(((pv[p] - base_v[p], p) for p in planets))
                dr = sorted(((pr[p] - base_r[p], p) for p in planets))
                print(f"  [{v} vs {BASE}] value: biggest drops " + ", ".join(f"{p} {d:+.1f}" for d, p in dv[:3])
                      + " | gains " + ", ".join(f"{p} {d:+.1f}" for d, p in dv[-3:]))
                print(f"  [{v} vs {BASE}] reached_by: drops " + ", ".join(f"{p} {d:+.2f}" for d, p in dr[:3])
                      + " | gains " + ", ".join(f"{p} {d:+.2f}" for d, p in dr[-3:]))
