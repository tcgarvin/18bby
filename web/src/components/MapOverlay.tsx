import { useMemo, useState } from "react";
import type { Board, GameState } from "../api";
import { corpColor, terrainByKey } from "../selectors";
import { HexMap } from "./HexMap";
import { MapLegend } from "./MapLegend";
import { Overlay } from "./Overlay";

const NO_HEXES = new Set<string>();

interface MapOverlayProps {
  state: GameState;
  board: Board;
  changedHexes: Map<string, string[]>;
  onClose: () => void;
}

/** The whole map over the current view, read-only, with a button per corporation to show its network. */
export function MapOverlay({ state, board, changedHexes, onClose }: MapOverlayProps) {
  const [focus, setFocus] = useState<string | null>(state.currentCorporation);
  const terrain = useMemo(() => terrainByKey(state.terrain), [state.terrain]);
  const floated = state.corporations.filter((c) => c.status === "floated");
  const tools = (
    <div className="focus-picker" role="group" aria-label="Show a network">
      {floated.map((corp) => (
        <button
          type="button"
          key={corp.id}
          className={`focus-picker__btn${focus === corp.id ? " focus-picker__btn--on" : ""}`}
          style={{ ["--corp" as string]: corpColor(state, corp.id) }}
          aria-pressed={focus === corp.id}
          onClick={() => setFocus((current) => (current === corp.id ? null : corp.id))}
        >
          {corp.id}
        </button>
      ))}
    </div>
  );
  return (
    <Overlay title="Map" tools={floated.length > 0 ? tools : undefined} wide onClose={onClose}>
      <div className="overlay-map">
        <div className="overlay-map__map">
          <HexMap
            board={board}
            tiles={state.tiles}
            terrain={terrain}
            nebulaChartSurcharge={state.config.nebulaChartSurcharge}
            corporations={state.corporations}
            focusCorp={focus}
            actionableHexes={NO_HEXES}
            selectedHex={null}
            preview={null}
            changedHexes={changedHexes}
            onHexClick={() => undefined}
            deathStar={state.deathStar}
            facilities={state.facilities}
          />
        </div>
        <MapLegend state={state} focusCorp={focus} />
      </div>
    </Overlay>
  );
}
