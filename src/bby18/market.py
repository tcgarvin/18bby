"""A one-dimensional stock price track."""

from __future__ import annotations

from bby18.config import GameConfig


class StockTrack:
    def __init__(self, config: GameConfig) -> None:
        self.prices = config.stock_track
        for par in config.par_prices:
            if par not in self.prices:
                raise ValueError(f"Par price {par} is not on the stock track")

    def index_of(self, price: int) -> int:
        try:
            return self.prices.index(price)
        except ValueError:
            raise ValueError(f"{price} is not on the stock track") from None

    def price_at(self, index: int) -> int:
        return self.prices[index]

    def step(self, index: int, delta: int) -> int:
        """Move ``delta`` steps along the track, clamped to its ends."""
        return max(0, min(len(self.prices) - 1, index + delta))
