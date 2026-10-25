import type { Action, CorporationState, GameState } from "../api";
import { corporationColor } from "../colors";
import { useHotkeys } from "../hotkeys";
import { Help } from "./Help";

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
  useHotkeys(Object.fromEntries(choices.map((action, i) => [String(i + 1), () => (busy ? false : onAct(action))])));

  return (
    <div className="actions">
      <p className="actions__lead">
        <strong style={{ color }}>{corp.id}</strong> earns <strong className="num">{total}</strong>
        {total > 0 && <> ({perShare}/share)</>}.
        <Help topic="revenue" />
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
      <p className="actions__hint">
        Pay <Help topic="dividend" /> · Withhold <Help topic="withhold" />
      </p>
      <div className="btn-row">
        {choices.map((action, i) => {
          const pay = action.choice === "pay";
          const preview = corp.dividendPreview;
          const next = preview === null ? corp.price : pay ? preview.pay : preview.withhold;
          return (
            <button
              type="button"
              key={action.choice}
              className={`btn${pay ? " btn--primary" : ""}`}
              disabled={busy}
              onClick={() => onAct(action)}
            >
              <span>
                {pay ? `Pay ${total}` : "Withhold"}
                <kbd>{i + 1}</kbd>
              </span>
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
