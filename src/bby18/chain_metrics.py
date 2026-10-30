"""Per-game measurements of the supply-chain rules, for balance sweeps.

``ChainTally`` is filled by ``DeathStarRecorder`` as the game is played: at every dividend move
it reads the chains the corporation ran (``Game.revenue``), and at every surrender move what the
corporation gave up. ``ChainMetrics.to_row`` gives the flat ``chain.*`` fields of a sweep row;
games without the chain rules have none.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from bby18.game import Game
from bby18.state import Corporation

ROW_PREFIX = "chain."
"""Every chain row field starts with this; rows of games without the chain rules have none."""

LONGEST_COUNTED_CHAIN = 4
"""Chains are counted by stops up to this many; the commodity order allows no longer ones."""


@dataclass
class ChainTally:
    """Running counts over one game's operating turns and seizures."""

    turns: int = 0
    """Operating turns that ran at least one chain."""
    chains_by_stops: dict[int, int] = field(
        default_factory=lambda: dict.fromkeys(range(2, LONGEST_COUNTED_CHAIN + 1), 0)
    )
    """Chains run, typed, contract and basic alike, by number of stops."""
    basic_chains: int = 0
    """Basic routes run (always two stops)."""
    contract_chains: int = 0
    """Chains run that end at the construction site."""
    regional_chains: int = 0
    """Chains run that earned the regional bonus."""
    revenue: int = 0
    """Revenue of every chain run (regional bonuses included)."""
    multi_stop_revenue: int = 0
    """Revenue of chains with a middle stop."""
    regional_revenue: int = 0
    """Regional bonuses earned."""
    surrenders: int = 0
    """Facilities corporations surrendered at seizures."""
    surrenders_of_middle_stops: int = 0
    """Surrendered facilities that were a middle stop of a chain the corporation was running:
    the seizure broke a chain."""
    surrenders_lost_revenue: int = 0
    """Revenue a turn lost to surrenders, at the moment of each: what the corporation's chains
    earned before minus after."""

    def record_turn(self, game: Game, corp: Corporation) -> None:
        """Count the chains ``corp`` runs now; called at its dividend move."""
        chains = game.revenue(corp).chains
        if not chains:
            return
        self.turns += 1
        for chain in chains:
            stops = len(chain.stops)
            if stops > LONGEST_COUNTED_CHAIN:
                raise ValueError(f"A chain of {stops} stops is longer than the rules allow")
            self.chains_by_stops[stops] += 1
            self.basic_chains += int(not any(l.typed or l.contract for l in chain.links))
            self.contract_chains += int(chain.links[-1].contract)
            self.regional_chains += int(chain.regional > 0)
            self.revenue += chain.value
            self.regional_revenue += chain.regional
            if stops > 2:
                self.multi_stop_revenue += chain.value

    def record_surrender(
        self, before_middles: frozenset[str], before: int, game: Game, corp: Corporation
    ) -> None:
        """Count one surrender by ``corp``: ``before_middles`` names the middle stops of the
        chains it ran just before, ``before`` their revenue."""
        self.surrenders += 1
        self.surrenders_lost_revenue += before - game.revenue(corp).total
        broke = before_middles - middle_stops_run(game, corp)
        self.surrenders_of_middle_stops += int(bool(broke))


def middle_stops_run(game: Game, corp: Corporation) -> frozenset[str]:
    """Names of the planets that are middle stops of chains ``corp`` runs now."""
    return frozenset(stop.name for chain in game.revenue(corp).chains for stop in chain.stops[1:-1])


@dataclass(frozen=True)
class ChainMetrics:
    """What one game under the chain rules did with chains."""

    turns: int
    chains_2: int
    chains_3: int
    chains_4: int
    basic_chains: int
    contract_chains: int
    regional_chains: int
    revenue: int
    multi_stop_revenue: int
    regional_revenue: int
    surrenders: int
    surrenders_of_middle_stops: int
    surrenders_lost_revenue: int

    @classmethod
    def of(cls, tally: ChainTally) -> ChainMetrics:
        by_stops = tally.chains_by_stops
        return cls(
            turns=tally.turns,
            chains_2=by_stops[2],
            chains_3=by_stops[3],
            chains_4=by_stops[4],
            basic_chains=tally.basic_chains,
            contract_chains=tally.contract_chains,
            regional_chains=tally.regional_chains,
            revenue=tally.revenue,
            multi_stop_revenue=tally.multi_stop_revenue,
            regional_revenue=tally.regional_revenue,
            surrenders=tally.surrenders,
            surrenders_of_middle_stops=tally.surrenders_of_middle_stops,
            surrenders_lost_revenue=tally.surrenders_lost_revenue,
        )

    def to_row(self) -> dict[str, int]:
        """Flat ``chain.*`` fields for a sweep row."""
        return {f"{ROW_PREFIX}{name}": value for name, value in asdict(self).items()}
