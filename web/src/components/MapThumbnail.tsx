import type { Board, GameState } from "../api";
import { terrainByKey } from "../selectors";
import { HexMap } from "./HexMap";

const NO_HEXES = new Set<string>();
const NO_CHANGES = new Map<string, string[]>();

/** A small, non-interactive map that opens the full map when clicked. */
export function MapThumbnail({ state, board, onOpen }: { state: GameState; board: Board; onOpen: () => void }) {
  return (
    <button type="button" className="mapthumb" onClick={onOpen} title="Open the map (M)">
      <HexMap
        board={board}
        tiles={state.tiles}
        terrain={terrainByKey(state.terrain)}
        nebulaChartSurcharge={state.config.nebulaChartSurcharge}
        corporations={state.corporations}
        focusCorp={null}
        actionableHexes={NO_HEXES}
        selectedHex={null}
        preview={null}
        changedHexes={NO_CHANGES}
        onHexClick={() => undefined}
        label="Map overview"
      />
      <span className="mapthumb__cta">
        Open map <kbd>M</kbd>
      </span>
    </button>
  );
}
