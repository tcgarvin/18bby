import type { GameState } from "../api";
import { corporationColor } from "../colors";

/** The linear share-price track with a marker per started corporation. */
export function StockTrack({ state }: { state: GameState }) {
  const corpIds = state.corporations.map((c) => c.id);
  const started = state.corporations.filter((c) => c.status !== "unstarted");
  const parSet = new Set(state.config.parPrices);
  return (
    <section className="panel">
      <h2 className="panel__title">Stock track</h2>
      <ol className="track" style={{ gridTemplateColumns: `repeat(${state.stockTrack.length}, minmax(0, 1fr))` }}>
        {state.stockTrack.map((price) => {
          const here = started.filter((c) => c.price === price);
          return (
            <li key={price} className={`track__cell${parSet.has(price) ? " track__cell--par" : ""}`}>
              <span className="track__price num">{price}</span>
              <span className="track__markers">
                {here.map((c) => (
                  <span key={c.id} className="track__marker" style={{ background: corporationColor(c.id, corpIds) }} title={`${c.id} at ${price}`}>
                    {c.id}
                  </span>
                ))}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
