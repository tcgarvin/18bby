"""Player-facing actions for stock and operating rounds."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from bby18.hexgrid import Direction, Hex


class ShareSource(Enum):
    IPO = "ipo"
    POOL = "pool"


@dataclass(frozen=True)
class BuyShare:
    corp_id: str
    source: ShareSource
    par: int = 0
    """Par price, required only when this purchase starts the corporation."""


@dataclass(frozen=True)
class SellShares:
    corp_id: str
    count: int


@dataclass(frozen=True)
class PassStock:
    pass


StockAction = BuyShare | SellShares | PassStock


@dataclass(frozen=True)
class Chart:
    hex: Hex
    exits: frozenset[Direction]
    cost: int = 0

    def __str__(self) -> str:
        return f"chart {self.hex} exits {'/'.join(d.name for d in sorted(self.exits))}"


@dataclass(frozen=True)
class Upgrade:
    hex: Hex
    new_exit: Direction
    cost: int = 0

    def __str__(self) -> str:
        return f"upgrade {self.hex} add {self.new_exit.name}"


@dataclass(frozen=True)
class ExtendService:
    hex: Hex
    cost: int = 0

    def __str__(self) -> str:
        return f"service {self.hex}"


@dataclass(frozen=True)
class NoNetworkAction:
    cost: int = 0

    def __str__(self) -> str:
        return "no network action"


NetworkAction = Chart | Upgrade | ExtendService | NoNetworkAction


@dataclass(frozen=True)
class BuyFleet:
    """Buy one fleet from the shared supply at ``cost``, the current fleet price."""

    cost: int

    def __str__(self) -> str:
        return f"buy a fleet for {self.cost}"


@dataclass(frozen=True)
class FinishFleets:
    """End the fleet step and go on to revenue."""

    def __str__(self) -> str:
        return "finish buying fleets"


FleetAction = BuyFleet | FinishFleets
