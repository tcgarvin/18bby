import type { GameState } from "../api";
import { corporationColor } from "../colors";

/** The two-dimensional stock market with a marker per started corporation. */
export function StockMarket({ state }: { state: GameState }) {
  const corpIds = state.corporations.map((c) => c.id);
  const started = state.corporations.filter((c) => c.marketCell !== null);
  const parSet = new Set(state.config.parPrices);
  const width = Math.max(...state.stockMarket.map((row) => row.length));
  return (
    <section className="panel">
      <h2 className="panel__title">Stock market</h2>
      <p className="muted market__hint">
        Paying moves right (two columns for a big payout), withholding left; selling moves down, a sold-out
        corporation moves up.
      </p>
      <div className="market">
        <ol className="track" style={{ gridTemplateColumns: `repeat(${width}, minmax(34px, 1fr))` }}>
          {state.stockMarket.flatMap((row, r) =>
            Array.from({ length: width }, (_, c) => {
              if (c >= row.length) return <li key={`${r}-${c}`} className="track__cell track__cell--empty" aria-hidden />;
              const price = row[c];
              const here = started.filter((corp) => corp.marketCell?.[0] === r && corp.marketCell?.[1] === c);
              const par = c === state.parColumn && parSet.has(price);
              return (
                <li key={`${r}-${c}`} className={`track__cell${par ? " track__cell--par" : ""}`}>
                  <span className="track__price num">{price}</span>
                  <span className="track__markers">
                    {here.map((corp) => (
                      <span
                        key={corp.id}
                        className="track__marker"
                        style={{ background: corporationColor(corp.id, corpIds) }}
                        title={`${corp.id} at ${price}`}
                      >
                        {corp.id}
                      </span>
                    ))}
                  </span>
                </li>
              );
            }),
          )}
        </ol>
      </div>
    </section>
  );
}
