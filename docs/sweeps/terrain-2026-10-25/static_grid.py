from dataclasses import replace
from bby18.config import DEFAULT_CONFIG as C
from bby18.terrain_report import terrain_report
print(f"{'ast':>5s}{'neb':>5s}{'patch':>6s} {'share costlier':>15s} {'mean extra':>11s}")
for ast, neb, patch in [(0.15,0.15,3),(0.15,0.15,1),(0.15,0.15,5),(0.25,0.15,3),(0.25,0.25,3),(0.10,0.10,3),(0.15,0.0,3),(0.0,0.15,3),(0.35,0.15,3),(0.25,0.25,5)]:
    r = terrain_report(range(1, 151), replace(C, asteroid_fraction=ast, nebula_fraction=neb, terrain_patch_size=patch))
    print(f"{ast:5.2f}{neb:5.2f}{patch:6d} {r['share_of_cheap_pairs_made_costlier']:15.3f} {r['mean_extra_cost_per_cheap_pair']:11.1f}")
