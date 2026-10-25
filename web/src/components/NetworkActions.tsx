import type { Action, Axial, CorporationState, GameState, HexAction, TileState } from "../api";
import { corporationColor } from "../colors";
import { hexKey } from "../hex";
import { useHotkeys } from "../hotkeys";
import { hexActionsByKey } from "../selectors";
import { TilePreview } from "./TilePreview";
import { Help } from "./Help";

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
  const keys: Record<string, () => void | false> = {
    p: () => (noAction && !busy ? onAct(noAction) : false),
  };
  options.slice(0, 9).forEach((action, i) => {
    keys[String(i + 1)] = () => (busy ? false : onAct(action));
  });
  useHotkeys(keys);
  const counts = { chart: 0, upgrade: 0, service: 0 };
  for (const actions of byKey.values()) {
    for (const a of actions) counts[a.type] += 1;
  }

  return (
    <div className="actions">
      <p className="actions__lead">
        Network action {state.networkActionsTaken + 1} of {state.config.networkActionsPerTurn} for{" "}
        <strong style={{ color }}>{corp.id}</strong>. Treasury{" "}
        <strong className="num">{corp.treasury}</strong>. Chart {state.config.chartCost} · Upgrade{" "}
        {state.config.upgradeCost} · Service {state.config.serviceCost}.
        <Help topic="networkAction" />
      </p>
      <p className="actions__hint">
        Chart <Help topic="chart" /> · Upgrade <Help topic="upgrade" /> · Service <Help topic="service" /> · Exits{" "}
        <Help topic="lanes" />
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
              close <kbd>Esc</kbd>
            </button>
          </div>
          <div className="hex-options__grid">
            {options.map((action, i) => (
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
                <span className="tile-option__cost num">
                  {action.cost}
                  {i < 9 && <kbd>{i + 1}</kbd>}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {noAction && (
        <button type="button" className="btn" disabled={busy} onClick={() => onAct(noAction)}>
          <span>
            {state.networkActionsTaken > 0 ? "End network actions" : "No network action"} <kbd>P</kbd>
          </span>
        </button>
      )}
    </div>
  );
}
