import type { Action, Axial, CorporationState, GameState, HexAction, TileState } from "../api";
import { laneArrivals } from "../facilities";
import { hexKey } from "../hex";
import { useHotkeys } from "../hotkeys";
import { corpColor, hexActionsByKey, playerName, terrainByKey } from "../selectors";
import { TilePreview } from "./TilePreview";
import { Help } from "./Help";

interface NetworkActionsProps {
  state: GameState;
  corp: CorporationState;
  selectedHex: Axial | null;
  /** Offer the hex options and "No network action"; false shows a read-only summary. */
  interactive: boolean;
  busy: boolean;
  keyboard: boolean;
  onSelectHex: (hex: Axial | null) => void;
  onPreview: (action: HexAction | null) => void;
  onAct: (action: Action) => void;
}

function describe(action: HexAction): string {
  if (action.type === "chart") return `Chart ${action.exits.join("–")}`;
  if (action.type === "upgrade") return `Add ${action.exit} exit`;
  return "Extend service";
}

/** The operating corporation's network step: actions left, costs, and the picked hex's options. */
export function NetworkActions(props: NetworkActionsProps) {
  const { state, corp, selectedHex, interactive, busy, keyboard, onSelectHex, onPreview, onAct } = props;
  const byKey = hexActionsByKey(state.legalActions);
  const terrain = terrainByKey(state.terrain);
  const hasNebula = state.terrain.some((t) => t.kind === "nebula");
  const noAction = state.legalActions.find((a) => a.type === "no_action");
  const color = corpColor(state, corp.id);
  const options = interactive && selectedHex ? (byKey.get(hexKey(selectedHex)) ?? []) : [];
  const tile: TileState | undefined = selectedHex
    ? state.tiles.find((t) => hexKey(t.hex) === hexKey(selectedHex))
    : undefined;
  const keys: Record<string, () => void | false> = {
    p: () => (noAction && !busy ? onAct(noAction) : false),
  };
  options.slice(0, 9).forEach((action, i) => {
    keys[String(i + 1)] = () => (busy ? false : onAct(action));
  });
  useHotkeys(keys, interactive && keyboard);
  const counts = { chart: 0, upgrade: 0, service: 0 };
  for (const actions of byKey.values()) {
    for (const a of actions) counts[a.type] += 1;
  }
  const perTurn = state.config.networkActionsPerTurn;

  return (
    <div className="netpanel">
      <div className="netpanel__steps" aria-label={`Network action ${state.networkActionsTaken + 1} of ${perTurn}`}>
        <span className="netpanel__label">
          Network action
          <Help topic="networkAction" />
        </span>
        {Array.from({ length: perTurn }, (_, i) => (
          <span
            key={i}
            className={`netpanel__pip${i < state.networkActionsTaken ? " netpanel__pip--used" : ""}${i === state.networkActionsTaken ? " netpanel__pip--now" : ""}`}
          />
        ))}
        <span className="netpanel__count num">
          {Math.min(state.networkActionsTaken + 1, perTurn)} of {perTurn}
        </span>
      </div>
      <dl className="netpanel__costs">
        <div>
          <dt>
            Chart
            <Help topic="chart" />
          </dt>
          <dd className="num">
            {state.config.chartCost}
            {hasNebula && <span className="netpanel__nebula">+{state.config.nebulaChartSurcharge} nebula</span>}
          </dd>
        </div>
        <div>
          <dt>
            Upgrade
            <Help topic="upgrade" />
          </dt>
          <dd className="num">{state.config.upgradeCost}</dd>
        </div>
        <div>
          <dt>
            Service
            <Help topic="service" />
          </dt>
          <dd className="num">{state.config.serviceCost}</dd>
        </div>
      </dl>

      {!interactive ? (
        <p className="netpanel__hint">{playerName(state, corp.president)} is choosing where to build…</p>
      ) : selectedHex && options.length > 0 ? (
        <div className="hex-options">
          <div className="hex-options__head">
            <span>
              Hex ({selectedHex[0]}, {selectedHex[1]}){terrain.get(hexKey(selectedHex)) === "nebula" ? " · nebula" : ""}
              {tile ? ` · charted ${tile.exits.join("/")}` : " · uncharted"}
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
                {laneArrivals(action, state.facilities).map((arrival) => (
                  <span
                    key={arrival.planet}
                    className={`tile-option__arrival${arrival.claims ? "" : " tile-option__arrival--dangles"}`}
                    title={
                      arrival.claims
                        ? `This lane claims one of ${arrival.planet}'s open exits`
                        : `${arrival.planet} has no open exit: this lane would dangle there until a facility gives it one`
                    }
                  >
                    {arrival.claims ? `claims ${arrival.planet}` : `dangles at ${arrival.planet}`}
                  </span>
                ))}
                <span className="tile-option__cost num">
                  {action.cost}
                  {action.type === "chart" && terrain.get(hexKey(action.hex)) === "nebula" && (
                    <span
                      className="tile-option__nebula"
                      title={`Includes ${state.config.nebulaChartSurcharge} extra for charting a nebula`}
                    >
                      nebula
                    </span>
                  )}
                  {i < 9 && <kbd>{i + 1}</kbd>}
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <p className="netpanel__hint">
          {byKey.size > 0 ? (
            <>
              Pick a highlighted hex on the map: <strong>{byKey.size}</strong> hexes with {counts.chart} chart,{" "}
              {counts.upgrade} upgrade and {counts.service} service options.
              <Help topic="lanes" />
            </>
          ) : (
            "No affordable or connected network actions."
          )}
        </p>
      )}

      {interactive && noAction && (
        <button type="button" className="btn btn--block" disabled={busy} onClick={() => onAct(noAction)}>
          <span>
            {state.networkActionsTaken > 0 ? "End network actions" : "No network action"} <kbd>P</kbd>
          </span>
        </button>
      )}
    </div>
  );
}
