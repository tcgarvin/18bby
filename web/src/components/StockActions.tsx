import { useState } from "react";
import type { Action, GameState, SellAction } from "../api";
import { corporationColor } from "../colors";
import { findCorporation, tradeOptions } from "../selectors";

interface StockActionsProps {
  state: GameState;
  busy: boolean;
  onAct: (action: Action) => void;
}

export function StockActions({ state, busy, onAct }: StockActionsProps) {
  const pass = state.legalActions.find((a) => a.type === "pass");
  const corpIds = state.corporations.map((c) => c.id);
  const options = tradeOptions(state);

  return (
    <div className="actions">
      {options.length === 0 && <p className="muted">No legal buys or sells.</p>}
      {options.map((option) => {
        const corp = findCorporation(state, option.corpId);
        if (!corp) return null;
        const color = corporationColor(corp.id, corpIds);
        return (
          <div key={option.corpId} className="trade">
            <div className="trade__corp">
              <span className="chip" style={{ background: color }}>
                {corp.id}
              </span>
              <span className="muted">{corp.status === "unstarted" ? "unstarted" : `price ${corp.price}`}</span>
            </div>
            <div className="trade__buttons">
              {option.ipoBuys.map((action) => (
                <button type="button" key={`ipo-${action.par ?? 0}`} className="btn btn--small" disabled={busy} onClick={() => onAct(action)}>
                  {action.par ? `Par ${action.par}` : `IPO ${corp.par}`}
                </button>
              ))}
              {option.poolBuy && (
                <button type="button" className="btn btn--small" disabled={busy} onClick={() => option.poolBuy && onAct(option.poolBuy)}>
                  Pool {corp.price}
                </button>
              )}
              {option.sells.length > 0 && <SellControl sells={option.sells} busy={busy} onAct={onAct} />}
            </div>
          </div>
        );
      })}
      {pass && (
        <button type="button" className="btn" disabled={busy} onClick={() => onAct(pass)}>
          Pass
        </button>
      )}
    </div>
  );
}

function SellControl({ sells, busy, onAct }: { sells: SellAction[]; busy: boolean; onAct: (a: Action) => void }) {
  const [index, setIndex] = useState(0);
  const chosen = sells[Math.min(index, sells.length - 1)];
  return (
    <span className="sell">
      <select value={Math.min(index, sells.length - 1)} onChange={(e) => setIndex(Number(e.target.value))} disabled={busy} aria-label="Shares to sell">
        {sells.map((s, i) => (
          <option key={s.count} value={i}>
            {s.count}
          </option>
        ))}
      </select>
      <button type="button" className="btn btn--small btn--sell" disabled={busy} onClick={() => onAct(chosen)}>
        Sell
      </button>
    </span>
  );
}
