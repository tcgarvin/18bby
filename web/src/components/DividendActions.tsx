import type { Action, CorporationState, GameState } from "../api";
import { corporationColor } from "../colors";
import { priceAfter } from "../selectors";

interface DividendActionsProps {
  state: GameState;
  corp: CorporationState;
  busy: boolean;
  onAct: (action: Action) => void;
}

export function DividendActions({ state, corp, busy, onAct }: DividendActionsProps) {
  const color = corporationColor(corp.id, state.corporations.map((c) => c.id));
  const { total, pairs } = corp.revenue;
  const perShare = total / state.config.sharesPerCorporation;
  const choices = state.legalActions.filter((a) => a.type === "dividend");

  return (
    <div className="actions">
      <p className="actions__lead">
        <strong style={{ color }}>{corp.id}</strong> earns <strong className="num">{total}</strong>
        {total > 0 && <> ({perShare}/share)</>}.
      </p>
      {pairs.length > 0 ? (
        <table className="pairs">
          <tbody>
            {pairs.map((pair) => (
              <tr key={`${pair.a}-${pair.b}`}>
                <td>
                  {pair.a} ↔ {pair.b}
                </td>
                <td className="muted">{pair.typed ? "typed" : "basic"}</td>
                <td className="num">{pair.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">No scoring pairs yet.</p>
      )}
      <div className="btn-row">
        {choices.map((action) => {
          const pay = action.choice === "pay";
          const next = priceAfter(state.stockTrack, corp.price, pay ? 1 : -1);
          return (
            <button
              type="button"
              key={action.choice}
              className={`btn${pay ? " btn--primary" : ""}`}
              disabled={busy}
              onClick={() => onAct(action)}
            >
              {pay ? `Pay ${total}` : "Withhold"}
              <span className="btn__sub num">
                price {corp.price} → {next}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
