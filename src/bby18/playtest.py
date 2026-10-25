"""Run many bot games and summarize what happened."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from statistics import mean

from bby18.board import Terrain
from bby18.bots import GreedyBot, GreedyPolicy, RandomBot
from bby18.config import GameConfig
from bby18.game import Game
from bby18.metrics import (
    CorpMetrics,
    StockCounts,
    PlanetMetrics,
    corporation_metrics,
    final_revenue_split,
    near_pair_links,
    planet_coverage,
    planet_metrics,
    worth_spread,
)
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
    winner_margin: float
    """Winner's worth minus the runner-up's, as a fraction of mean worth."""
    worth_cv: float
    """Population standard deviation of final worth over its mean."""
    corps: dict[str, CorpMetrics]
    """Every corporation, floated or not."""
    stock: StockCounts
    final_typed_revenue: int
    final_basic_revenue: int
    planets_total: int
    planets_reached: int
    """Planets reached by at least one floated corporation."""
    region_reached: dict[str, int]
    region_total: dict[str, int]
    planets: dict[str, PlanetMetrics]
    near_pairs: int
    """Planet pairs within a few hexes of each other (a fixed property of the board)."""
    near_pairs_linked: int
    """Near pairs that one floated corporation's final network connects."""
    near_pairs_stranded: int
    """Near pairs with a planet that no floated corporation reaches."""
    asteroid_hexes: int
    nebula_hexes: int

    @property
    def planets_reached_fraction(self) -> float:
        return self.planets_reached / self.planets_total

    def to_row(self) -> dict[str, int | float | bool | str]:
        """A flat, JSON-serializable record. Nested values use dotted keys."""
        row: dict[str, int | float | bool | str] = {
            "winner": self.winner,
            "winner_margin": self.winner_margin,
            "worth_cv": self.worth_cv,
            "mean_worth": mean(self.worth.values()),
            "tiles_charted": self.tiles_charted,
            "junctions": self.junctions,
            "shared_tiles": self.shared_tiles,
            "floated": self.floated,
            "final_typed_revenue": self.final_typed_revenue,
            "final_basic_revenue": self.final_basic_revenue,
            "planets_total": self.planets_total,
            "planets_reached": self.planets_reached,
            "planets_reached_fraction": self.planets_reached_fraction,
        }
        row.update(asdict(self.stock))
        for seat, value in self.worth.items():
            row[f"worth.{seat}"] = value
        for corp_id, metrics in self.corps.items():
            for name, value in asdict(metrics).items():
                row[f"corp.{corp_id}.{name}"] = value
        for region, count in self.region_reached.items():
            row[f"region_reached.{region}"] = count
        for region, count in self.region_total.items():
            row[f"region_total.{region}"] = count
        for name, planet in self.planets.items():
            row[f"planet.{name}.reached_by"] = planet.reached_by
            row[f"planet.{name}.value"] = planet.value
        row["near_pairs"] = self.near_pairs
        row["near_pairs_linked"] = self.near_pairs_linked
        row["near_pairs_stranded"] = self.near_pairs_stranded
        row["asteroid_hexes"] = self.asteroid_hexes
        row["nebula_hexes"] = self.nebula_hexes
        return row


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


def _greedy(policy: GreedyPolicy) -> Callable[[random.Random], Decider]:
    return lambda rng: GreedyBot(rng, policy)


BOT_KINDS: dict[str, Callable[[random.Random], Decider]] = {
    "greedy": _greedy(GreedyPolicy()),
    "random": RandomBot,
    "greedy-path": _greedy(GreedyPolicy(routing="path")),
    "greedy-rs": _greedy(
        GreedyPolicy(start_order="random", par_choice="random", max_presidencies=2)
    ),
    "greedy-best": _greedy(GreedyPolicy(start_order="best_home", max_presidencies=2)),
    "greedy-hold": _greedy(GreedyPolicy(withhold_when_revenue_below=60, pay_threshold=4)),
    "greedy-sell": _greedy(GreedyPolicy(sell_losers=True, start_order="random")),
    "greedy-max": _greedy(GreedyPolicy(par_choice="max", start_order="random", max_presidencies=2)),
}
"""Named bot kinds for playtests and sweeps. Each builds one seat's decider from its own rng."""

MIX_PREFIX = "mix:"


def seat_kinds(bot: str, player_count: int) -> list[str]:
    """The bot kind for each seat. ``"mix:a,b"`` assigns kinds round-robin from seat 1;
    any other string is one kind for every seat. Unknown kinds raise ``ValueError``."""
    if bot.startswith(MIX_PREFIX):
        kinds = [k.strip() for k in bot[len(MIX_PREFIX) :].split(",")]
        if not kinds or any(not k for k in kinds):
            raise ValueError(f"Bad mixed bot string {bot!r}; use mix:kind1,kind2,...")
    else:
        kinds = [bot]
    unknown = [k for k in kinds if k not in BOT_KINDS]
    if unknown:
        raise ValueError(f"Unknown bot kind {unknown[0]!r}; choose from {', '.join(BOT_KINDS)}")
    return [kinds[i % len(kinds)] for i in range(player_count)]


def make_deciders(game: Game, kind: str, rng: random.Random) -> dict[str, Decider]:
    kinds = seat_kinds(kind, len(game.players))
    return {p.id: BOT_KINDS[k](random.Random(rng.random())) for p, k in zip(game.players, kinds)}


def play_one(
    seed: int, player_count: int, kind: str, config: GameConfig
) -> tuple[Game, GameSummary]:
    rng = random.Random(seed)
    game = Game.new([f"Player {i + 1}" for i in range(player_count)], config, seed)
    run_game(game, make_deciders(game, kind, rng))
    return game, summarize_game(game, seed)


def summarize_game(game: Game, seed: int) -> GameSummary:
    """Measure a finished game."""
    worth = {p.id: game.player_worth(p) for p in game.players}
    winner = max(worth, key=lambda k: worth[k])
    margin, cv = worth_spread(worth)
    tiles = game.network.tiles()
    typed, basic = final_revenue_split(game)
    coverage = planet_coverage(game)
    counts = corporation_metrics(game)
    near_pairs, near_linked, near_stranded = near_pair_links(game)
    terrain = game.board.terrain.values()
    return GameSummary(
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
        winner_margin=margin,
        worth_cv=cv,
        corps=counts.corps,
        stock=counts.stock,
        final_typed_revenue=typed,
        final_basic_revenue=basic,
        planets_total=coverage.planets_total,
        planets_reached=coverage.planets_reached,
        region_reached=coverage.region_reached,
        region_total=coverage.region_total,
        planets=planet_metrics(game),
        near_pairs=near_pairs,
        near_pairs_linked=near_linked,
        near_pairs_stranded=near_stranded,
        asteroid_hexes=sum(1 for t in terrain if t is Terrain.ASTEROID),
        nebula_hexes=sum(1 for t in terrain if t is Terrain.NEBULA),
    )


def play_many(games: int, player_count: int, kind: str, config: GameConfig, seed: int) -> Aggregate:
    agg = Aggregate()
    for i in range(games):
        _, summary = play_one(seed + i, player_count, kind, config)
        agg.games.append(summary)
    return agg
