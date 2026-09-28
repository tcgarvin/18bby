"""A two-dimensional stock market in the classic 18xx style.

Rows run from the top (highest prices) down; columns run left to right (rising prices). Rows may
be shorter than the top row: a row simply has no cells past its end. Dividends move a
corporation horizontally; stock-round demand moves it vertically.
"""

from __future__ import annotations

from dataclasses import dataclass

from bby18.config import GameConfig


@dataclass(frozen=True, order=True)
class MarketCell:
    row: int
    col: int


class StockMarket:
    def __init__(self, config: GameConfig) -> None:
        self.rows = config.stock_market
        if not self.rows or any(len(row) == 0 for row in self.rows):
            raise ValueError("The stock market needs at least one non-empty row")
        self._par_cells: dict[int, MarketCell] = {}
        col = config.par_column
        for row_index, row in enumerate(self.rows):
            if col < len(row) and row[col] in config.par_prices:
                self._par_cells[row[col]] = MarketCell(row_index, col)
        missing = set(config.par_prices) - set(self._par_cells)
        if missing:
            raise ValueError(f"Par prices {sorted(missing)} are not in market column {col}")

    def exists(self, row: int, col: int) -> bool:
        return 0 <= row < len(self.rows) and 0 <= col < len(self.rows[row])

    def price_at(self, cell: MarketCell) -> int:
        if not self.exists(cell.row, cell.col):
            raise ValueError(f"{cell} is not on the stock market")
        return self.rows[cell.row][cell.col]

    def par_cell(self, par: int) -> MarketCell:
        try:
            return self._par_cells[par]
        except KeyError:
            raise ValueError(f"{par} is not a par price") from None

    def right(self, cell: MarketCell, steps: int = 1) -> MarketCell:
        """Move right ``steps`` times. At the end of a row a move goes up instead; in the top
        right corner it stays."""
        for _ in range(steps):
            if self.exists(cell.row, cell.col + 1):
                cell = MarketCell(cell.row, cell.col + 1)
            else:
                cell = self.up(cell)
        return cell

    def left(self, cell: MarketCell, steps: int = 1) -> MarketCell:
        """Move left ``steps`` times. At the left edge a move goes down instead; in the bottom
        left corner it stays."""
        for _ in range(steps):
            if cell.col > 0:
                cell = MarketCell(cell.row, cell.col - 1)
            else:
                cell = self.down(cell)
        return cell

    def up(self, cell: MarketCell, steps: int = 1) -> MarketCell:
        """Move up ``steps`` rows, stopping at the top row."""
        for _ in range(steps):
            if self.exists(cell.row - 1, cell.col):
                cell = MarketCell(cell.row - 1, cell.col)
        return cell

    def down(self, cell: MarketCell, steps: int = 1) -> MarketCell:
        """Move down ``steps`` rows, stopping where the row below has no cell in this column."""
        for _ in range(steps):
            if self.exists(cell.row + 1, cell.col):
                cell = MarketCell(cell.row + 1, cell.col)
        return cell

    def top_price(self) -> int:
        return max(max(row) for row in self.rows)
