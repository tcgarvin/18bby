import json, sys
from collections import defaultdict
from statistics import mean
from dataclasses import replace
from bby18.board import load_board
from bby18.config import DEFAULT_CONFIG as C
from bby18.terrain import generate_terrain
from bby18.terrain_report import pair_costs

rows = [json.loads(l) for l in open(sys.argv[1])]
board = load_board()
names = [p.name for p in board.planets]
def access(seed, cfg):
    t = generate_terrain(board, seed, cfg)
    pc = pair_costs(board.with_terrain(t), cfg)
    out = {}
    for n in names:
        costs = sorted(c for (a, b), c in pc.items() if n in (a, b))
        out[n] = mean(costs[:3])
    return out
def pearson(x, y):
    mx, my = mean(x), mean(y)
    sx = sum((a-mx)**2 for a in x)**.5; sy = sum((b-my)**2 for b in y)**.5
    return sum((a-mx)*(b-my) for a, b in zip(x, y)) / (sx*sy)
def slope(x, y):
    mx, my = mean(x), mean(y)
    return sum((a-mx)*(b-my) for a, b in zip(x, y)) / sum((a-mx)**2 for a in x)
cache = {}
for bot in ("greedy-path", "greedy"):
    for variant, cfg in (("old", C), ("new", C), ("dense", replace(C, asteroid_fraction=.25, nebula_fraction=.25)), ("heavy", replace(C, asteroid_fraction=.35, nebula_fraction=.2, terrain_patch_size=5))):
        by_planet = {n: ([], [], []) for n in names}
        for r in rows:
            if r["bot"] != bot or r["variant"] != variant: continue
            key = (r["seed"], variant if variant != "old" else "new")
            if key not in cache:
                cache[key] = access(r["seed"], cfg if variant != "old" else C)
            a = cache[key]
            for n in names:
                by_planet[n][0].append(a[n]); by_planet[n][1].append(r[f"planet.{n}.reached_by"]); by_planet[n][2].append(r[f"planet.{n}.value"])
        xs, ys, vs = [], [], []
        for n in names:
            x, y, v = by_planet[n]
            mx, my, mv = mean(x), mean(y), mean(v)
            xs += [a - mx for a in x]; ys += [b - my for b in y]; vs += [c - mv for c in v]
        print(f"{bot:12s} {variant:6s} n={len(xs)}  within-planet r(access, reached_by)={pearson(xs, ys):+.3f}  slope per +50cr={slope(xs, ys)*50:+.3f} corps   r(access, value)={pearson(xs, vs):+.3f}  slope per +50cr={slope(xs, vs)*50:+.2f} credits")
