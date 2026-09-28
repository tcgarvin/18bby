import type { Action, Axial, CorporationState, GameState, HexAction, TileState } from "../api";
import { corporationColor } from "../colors";
import { hexKey } from "../hex";
import { hexActionsByKey } from "../selectors";
import { TilePreview } from "./TilePreview";

interface NetworkActionsProps {
  state: GameState;
  corp: CorporationState;
  selectedHex: Axial | null;
  busy: boolean;
  onSelectHex: (hex: Axial | null) => void;
  onPreview: (action: HexAction | null) => void;
  onAct: (action: Action) => void;
}

function describe(action: HexAction): string {
  if (action.type === "chart") return `Chart ${action.exits.join("–")}`;
  if (action.type === "upgrade") return `Add ${action.exit} exit`;
  return "Extend service";
}

export function NetworkActions({ state, corp, selectedHex, busy, onSelectHex, onPreview, onAct }: NetworkActionsProps) {
  const byKey = hexActionsByKey(state.legalActions);
  const noAction = state.legalActions.find((a) => a.type === "no_action");
  const color = corporationColor(corp.id, state.corporations.map((c) => c.id));
  const options = selectedHex ? (byKey.get(hexKey(selectedHex)) ?? []) : [];
  const tile: TileState | undefined = selectedHex
    ? state.tiles.find((t) => hexKey(t.hex) === hexKey(selectedHex))
    : undefined;
  const counts = { chart: 0, upgrade: 0, service: 0 };
  for (const actions of byKey.values()) {
    for (const a of actions) counts[a.type] += 1;
  }

  return (
    <div className="actions">
      <p className="actions__lead">
        One network action for <strong style={{ color }}>{corp.id}</strong>. Treasury{" "}
        <strong className="num">{corp.treasury}</strong>. Chart {state.config.chartCost} · Upgrade{" "}
        {state.config.upgradeCost} · Service {state.config.serviceCost}.
      </p>
      <p className="actions__hint">
        {byKey.size > 0
          ? `Click a highlighted hex on the map (${byKey.size} hexes: ${counts.chart} chart, ${counts.upgrade} upgrade, ${counts.service} service options).`
          : "No affordable or connected network actions."}
      </p>

      {selectedHex && options.length > 0 && (
        <div className="hex-options">
          <div className="hex-options__head">
            <span>
              Hex ({selectedHex[0]}, {selectedHex[1]}){tile ? ` · charted ${tile.exits.join("/")}` : " · uncharted"}
            </span>
            <button type="button" className="link" onClick={() => onSelectHex(null)}>
              close
            </button>
          </div>
          <div className="hex-options__grid">
            {options.map((action) => (
              <button
                type="button"
                key={JSON.stringify(action)}
                className="tile-option"
                disabled={busy}
                onMouseEnter={() => onPreview(action)}
                onMouseLeave={() => onPreview(null)}
                onFocus={() => onPreview(action)}
                onBlur={() => onPreview(null)}
                onClick={() => onAct(action)}
              >
                <TilePreview
                  existing={action.type === "chart" ? [] : (tile?.exits ?? [])}
                  added={action.type === "chart" ? action.exits : action.type === "upgrade" ? [action.exit] : []}
                  color={color}
                />
                <span className="tile-option__label">{describe(action)}</span>
                <span className="tile-option__cost num">{action.cost}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {noAction && (
        <button type="button" className="btn" disabled={busy} onClick={() => onAct(noAction)}>
          No network action
        </button>
      )}
    </div>
  );
}
