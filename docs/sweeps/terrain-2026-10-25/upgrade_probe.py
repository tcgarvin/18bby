import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from statistics import mean
from bby18 import playtest
from bby18.bots import GreedyBot, GreedyPolicy
from bby18.config import DEFAULT_CONFIG as C

def run(args):
    seed, up, cw = args
    playtest.BOT_KINDS["probe"] = lambda rng: GreedyBot(rng, GreedyPolicy(routing="path", cost_weight=cw))
    game, s = playtest.play_one(seed, 3, "probe", replace(C, upgrade_cost=up))
    ups = mean(m.upgrades for m in s.corps.values() if m.floated)
    return ups, mean(s.corp_revenue.values()), mean(s.corp_planets.values())

if __name__ == "__main__":
    with ProcessPoolExecutor(15) as pool:
        for cw in (0.1, 0.0):
            for up in (30, 50, 70):
                res = list(pool.map(run, [(s, up, cw) for s in range(1, 121)]))
                print(f"cost_weight={cw} upgrade={up}: upgrades/corp={mean(r[0] for r in res):.2f} revenue={mean(r[1] for r in res):.0f} planets={mean(r[2] for r in res):.2f}")
