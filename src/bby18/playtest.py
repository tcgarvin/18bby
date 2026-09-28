"""Run many bot games and summarize what happened."""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from statistics import mean

from bby18.bots import GreedyBot, RandomBot
from bby18.config import GameConfig
from bby18.game import Game
from bby18.runner import run_game
from bby18.session import Decider


@dataclass
class GameSummary:
    seed: int
    winner: str
    worth: dict[str, int]
    corp_revenue: dict[str, int]
    corp_price: dict[str, int]
    corp_planets: dict[str, int]
    tiles_charted: int
    junctions: int
    shared_tiles: int
    floated: int


@dataclass
class Aggregate:
    games: list[GameSummary] = field(default_factory=list)

    def report(self) -> str:
        if not self.games:
            return "no games"
        n = len(self.games)
        lines = [f"{n} games"]
        wins = Counter(g.winner for g in self.games)
        lines.append("wins by seat: " + ", ".join(f"{k} {v}" for k, v in sorted(wins.items())))
        lines.append(f"mean final worth: {mean(mean(g.worth.values()) for g in self.games):.0f}")
        lines.append(f"mean corporations floated: {mean(g.floated for g in self.games):.1f}")
        lines.append(f"mean tiles charted: {mean(g.tiles_charted for g in self.games):.1f}")
        lines.append(f"mean 3-exit junctions: {mean(g.junctions for g in self.games):.1f}")
        lines.append(
            f"mean tiles with 2+ corps serving: {mean(g.shared_tiles for g in self.games):.1f}"
        )
        corps = sorted({c for g in self.games for c in g.corp_revenue})
        lines.append("per corporation (mean final revenue / price / planets reached):")
        for c in corps:
            rev = mean(g.corp_revenue.get(c, 0) for g in self.games)
            price = mean(g.corp_price.get(c, 0) for g in self.games)
            planets = mean(g.corp_planets.get(c, 0) for g in self.games)
            lines.append(f"  {c}: {rev:.0f} / {price:.0f} / {planets:.1f}")
        return "\n".join(lines)


def make_deciders(game: Game, kind: str, rng: random.Random) -> dict[str, Decider]:
    deciders: dict[str, Decider] = {}
    for p in game.players:
        if kind == "greedy":
            deciders[p.id] = GreedyBot(random.Random(rng.random()))
        elif kind == "random":
            deciders[p.id] = RandomBot(random.Random(rng.random()))
        else:
            raise ValueError(f"Unknown bot kind {kind!r}")
    return deciders


def play_one(
    seed: int, player_count: int, kind: str, config: GameConfig
) -> tuple[Game, GameSummary]:
    rng = random.Random(seed)
    game = Game.new([f"Player {i + 1}" for i in range(player_count)], config)
    run_game(game, make_deciders(game, kind, rng))
    worth = {p.id: game.player_worth(p) for p in game.players}
    winner = max(worth, key=lambda k: worth[k])
    tiles = game.network.tiles()
    summary = GameSummary(
        seed=seed,
        winner=winner,
        worth=worth,
        corp_revenue={c.id: c.last_revenue for c in game.corporations.values() if c.floated},
        corp_price={c.id: game.price(c) for c in game.corporations.values() if c.floated},
        corp_planets={
            c.id: len(game.reachable_planets(c)) for c in game.corporations.values() if c.floated
        },
        tiles_charted=len(tiles),
        junctions=sum(1 for t in tiles.values() if len(t.exits) == 3),
        shared_tiles=sum(1 for h in tiles if len(game.network.corporations_serving(h)) >= 2),
        floated=sum(1 for c in game.corporations.values() if c.floated),
    )
    return game, summary


def play_many(games: int, player_count: int, kind: str, config: GameConfig, seed: int) -> Aggregate:
    agg = Aggregate()
    for i in range(games):
        _, summary = play_one(seed + i, player_count, kind, config)
        agg.games.append(summary)
    return agg
