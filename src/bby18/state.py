"""Mutable game entities: players and corporations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from bby18.config import CorporationSpec

NO_PLAYER = ""
"""Sentinel president id for a corporation nobody has bought into."""


class CorpStatus(Enum):
    UNSTARTED = "unstarted"
    PARRED = "parred"
    FLOATED = "floated"


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
    price_index: int = 0
    treasury: int = 0
    ipo_shares: int = 10
    pool_shares: int = 0
    president: str = NO_PLAYER
    float_order: int = -1
    last_revenue: int = 0

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def floated(self) -> bool:
        return self.status is CorpStatus.FLOATED
