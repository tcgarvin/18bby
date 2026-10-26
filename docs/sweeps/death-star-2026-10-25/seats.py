"""Seat effects and per-seed best strategy from tournament rows."""
import json, sys
from collections import defaultdict
from statistics import mean
path, variant = sys.argv[1], sys.argv[2]
seat_share = defaultdict(list); seat_win = defaultdict(list)
mirror_share = defaultdict(list)
by_seed = defaultdict(lambda: defaultdict(list))
for line in open(path):
    r = json.loads(line)
    if r["variant"] != variant: continue
    kinds = r["bot"].removeprefix("mix:").split(",")
    w = [r[f"worth.P{i+1}"] for i in range(3)]
    tot = sum(w) or 1
    for i, k in enumerate(kinds):
        s = w[i] / tot
        seat_share[i].append(s); seat_win[i].append(1 if w[i] == max(w) else 0)
        by_seed[r["seed"]][k].append(s)
    if len(set(kinds)) == 1:
        for i in range(3): mirror_share[i].append(w[i]/tot)
print(variant, "seat share", [round(100*mean(seat_share[i]),1) for i in range(3)],
      "seat win", [round(100*mean(seat_win[i]),1) for i in range(3)],
      "mirror-table seat share", [round(100*mean(mirror_share[i]),1) for i in range(3)])
for seed in sorted(by_seed):
    ranked = sorted(((mean(v), k) for k, v in by_seed[seed].items()), reverse=True)[:3]
    print("  seed", seed, " ".join(f"{k} {100*m:.1f}" for m, k in ranked))
