import type { GameState } from "../api";
import { corporationColor } from "../colors";
import { playerName } from "../selectors";

interface CorporationsPanelProps {
  state: GameState;
  focusCorp: string | null;
  onToggle: (corpId: string) => void;
}

export function CorporationsPanel({ state, focusCorp, onToggle }: CorporationsPanelProps) {
  const corpIds = state.corporations.map((c) => c.id);
  return (
    <section className="panel">
      <h2 className="panel__title">
        Corporations
        <span className="panel__aside">click to show network</span>
      </h2>
      <div className="corp-list">
        {state.corporations.map((corp) => {
          const color = corporationColor(corp.id, corpIds);
          const order = state.operatingOrder.indexOf(corp.id);
          const operating = corp.id === state.currentCorporation;
          return (
            <button
              type="button"
              key={corp.id}
              className={`corp${focusCorp === corp.id ? " corp--focused" : ""}${operating ? " corp--operating" : ""}`}
              style={{ ["--corp" as string]: color }}
              onClick={() => onToggle(corp.id)}
              aria-pressed={focusCorp === corp.id}
            >
              <div className="corp__head">
                <span className="chip" style={{ background: color }}>
                  {corp.id}
                </span>
                <span className="corp__name">{corp.name}</span>
                <span className={`status status--${corp.status}`}>{corp.status}</span>
              </div>
              <dl className="corp__stats">
                <div>
                  <dt>Price</dt>
                  <dd className="num">{corp.status === "unstarted" ? "—" : corp.price}</dd>
                </div>
                <div>
                  <dt>Par</dt>
                  <dd className="num">{corp.par || "—"}</dd>
                </div>
                <div>
                  <dt>Treasury</dt>
                  <dd className="num">{corp.treasury}</dd>
                </div>
                <div>
                  <dt>Last rev</dt>
                  <dd className="num">{corp.lastRevenue}</dd>
                </div>
                <div>
                  <dt>IPO / Pool</dt>
                  <dd className="num">
                    {corp.ipoShares} / {corp.poolShares}
                  </dd>
                </div>
                <div>
                  <dt>Order</dt>
                  <dd className="num">{order >= 0 ? `#${order + 1}` : "—"}</dd>
                </div>
              </dl>
              <div className="corp__foot">
                <span>
                  President <strong>{corp.president ? playerName(state, corp.president) : "none"}</strong>
                </span>
                <span className="muted">
                  {corp.homeworld}
                  {corp.status === "floated" && ` · reaches ${corp.reachablePlanets.length}`}
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
