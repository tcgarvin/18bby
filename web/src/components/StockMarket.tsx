import type { CSSProperties } from "react";
import type { GameState } from "../api";
import { corpColor } from "../selectors";

/** A rectangle of market cells, inclusive at both ends: [first, last]. */
export interface MarketWindow {
  rows: [number, number];
  cols: [number, number];
}

/** A dashed marker where a corporation's token would go, e.g. after paying or withholding. */
export interface MarketGhost {
  corpId: string;
  cell: [number, number];
  label: string;
  tone: "up" | "down" | "flat";
}

interface StockMarketProps {
  state: GameState;
  /** Draw only part of the market (the dividend view shows a slice around one token). */
  window?: MarketWindow;
  ghosts?: MarketGhost[];
  /** Dim every token but this corporation's. */
  emphasis?: string | null;
  /** Fill the parent's height instead of keeping the grid's own aspect ratio. */
  fill?: boolean;
}

/** Width over height of one cell. */
const CELL_ASPECT = 1.3;

function fullWindow(market: number[][]): MarketWindow {
  const width = Math.max(...market.map((row) => row.length));
  return { rows: [0, market.length - 1], cols: [0, width - 1] };
}

/**
 * The two-dimensional stock market with a token per started corporation.
 *
 * Tokens are positioned absolutely from their cell's row and column (as percentages of the
 * grid) and keyed by corporation, so a CSS transition on left/top slides a token between
 * cells when its price moves. Corporations sharing a cell split it into equal bands, top to
 * bottom (--slot of --count), so each stays legible at its real cell.
 */
export function StockMarket({ state, window, ghosts = [], emphasis = null, fill = false }: StockMarketProps) {
  const market = state.stockMarket;
  const view = window ?? fullWindow(market);
  const [r0, r1] = view.rows;
  const [c0, c1] = view.cols;
  const rows = r1 - r0 + 1;
  const cols = c1 - c0 + 1;
  const parSet = new Set(state.config.parPrices);
  const inView = ([r, c]: [number, number]) => r >= r0 && r <= r1 && c >= c0 && c <= c1;
  /**
   * The cell's box, or the `slot`th of `count` bands of it when corporations share the cell: stacked
   * top to bottom for two, in two columns for more (an odd last one spans the row).
   */
  const place = ([r, c]: [number, number], slot = 0, count = 1): CSSProperties => {
    const columns = count > 2 ? 2 : 1;
    const bands = Math.ceil(count / columns);
    const spans = columns === 2 && slot === count - 1 && count % 2 === 1;
    const column = columns === 2 && !spans ? slot % 2 : 0;
    const band = Math.floor(slot / columns);
    return {
      left: `${((c - c0 + (column / columns)) * 100) / cols}%`,
      top: `${((r - r0 + band / bands) * 100) / rows}%`,
      width: `${(spans ? 100 : 100 / columns) / cols}%`,
      height: `${100 / rows / bands}%`,
    };
  };

  // A closed corporation's shares have left the game, so it has no place on the market.
  const started = state.corporations.filter((c) => c.marketCell !== null && c.status !== "closed");
  const slotOf = new Map<string, number>();
  const crowd = new Map<string, number>();
  for (const corp of started) {
    const key = String(corp.marketCell);
    slotOf.set(corp.id, crowd.get(key) ?? 0);
    crowd.set(key, (crowd.get(key) ?? 0) + 1);
  }
  const countAt = (cell: [number, number]) => crowd.get(String(cell)) ?? 1;

  const frameStyle = {
    ["--cols" as string]: cols,
    ["--rows" as string]: rows,
    ["--ratio" as string]: (cols * CELL_ASPECT) / rows,
  } as CSSProperties;

  return (
    <div className={`market${fill ? " market--fill" : ""}`} style={frameStyle}>
      <div className="market__grid" role="img" aria-label="Stock market">
        {Array.from({ length: rows }, (_, i) =>
          Array.from({ length: cols }, (_, j) => {
            const r = r0 + i;
            const c = c0 + j;
            const price = market[r]?.[c];
            if (price === undefined) return <span key={`${r}-${c}`} className="mcell mcell--none" />;
            const par = c === state.parColumn && parSet.has(price);
            return (
              <span key={`${r}-${c}`} className={`mcell${par ? " mcell--par" : ""}`} title={par ? `Par ${price}` : undefined}>
                <span className="mcell__price num">{price}</span>
              </span>
            );
          }),
        )}
        {ghosts.filter((g) => inView(g.cell)).map((ghost) => (
          <span
            key={`ghost-${ghost.label}`}
            className={`mghost mghost--${ghost.tone}`}
            style={{ ...place(ghost.cell), ["--corp" as string]: corpColor(state, ghost.corpId) }}
          >
            <span className="mghost__ring" />
            <span className="mghost__label">{ghost.label}</span>
          </span>
        ))}
        {started.map((corp) => {
          const cell = corp.marketCell as [number, number];
          if (!inView(cell)) return null;
          const dimmed = emphasis !== null && emphasis !== corp.id;
          const slot = slotOf.get(corp.id) ?? 0;
          const count = countAt(cell);
          return (
            <span
              key={corp.id}
              data-market-token={corp.id}
              className={`mtoken${count > 1 ? " mtoken--shared" : ""}${dimmed ? " mtoken--dimmed" : ""}`}
              style={{
                ...place(cell, slot, count),
                ["--corp" as string]: corpColor(state, corp.id),
                ["--slot" as string]: slot,
                ["--count" as string]: count,
              }}
              title={`${corp.id} at ${corp.price}`}
            >
              <span className="mtoken__disc">
                {corp.id}
                <span className="mtoken__price">{corp.price}</span>
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
}
