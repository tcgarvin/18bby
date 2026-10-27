"""Mutable game entities: players and corporations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from bby18.config import CorporationSpec
from bby18.hexgrid import Hex
from bby18.market import MarketCell

NO_PLAYER = ""
"""Sentinel president id for a corporation nobody has bought into."""


class CorpStatus(Enum):
    UNSTARTED = "unstarted"
    PARRED = "parred"
    FLOATED = "floated"
    CLOSED = "closed"
    """Bankrupt under the experimental Death Star rules: its shares are gone and it never
    operates again."""


@dataclass
class Player:
    id: str
    name: str
    cash: int
    shares: dict[str, int] = field(default_factory=dict)

    def shares_in(self, corp_id: str) -> int:
        return self.shares.get(corp_id, 0)


@dataclass
class Corporation:
    spec: CorporationSpec
    status: CorpStatus = CorpStatus.UNSTARTED
    par: int = 0
    market_cell: MarketCell = MarketCell(0, 0)
    """Position on the stock market; meaningless until the corporation starts."""
    treasury: int = 0
    ipo_shares: int = 10
    pool_shares: int = 0
    president: str = NO_PLAYER
    float_order: int = -1
    last_revenue: int = 0
    fleets: int = 0
    """Fleets owned; each runs one revenue pair (Death Star rules only). Under the facility
    rules, the facilities it owns: ``Game`` keeps it equal to its entries in
    ``Game.facilities``, so pair capacity reads the same under both rules."""

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def floated(self) -> bool:
        return self.status is CorpStatus.FLOATED


@dataclass(frozen=True)
class Facility:
    """One facility on a planet (experimental facility rules)."""

    planet: Hex
    owner: str
    """The owning corporation's id, or ``EMPIRE`` once seized."""
    build_number: int
    """Order of building over the whole game, from 0; a later facility has a higher number."""
