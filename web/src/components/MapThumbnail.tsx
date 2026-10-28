import type { Board, GameState } from "../api";
import { terrainByKey } from "../selectors";
import { HexMap } from "./HexMap";

const NO_HEXES = new Set<string>();
const NO_CHANGES = new Map<string, string[]>();

/** A small, non-interactive map that switches the screen to the Map view when clicked. */
export function MapThumbnail({ state, board, onOpen }: { state: GameState; board: Board; onOpen: () => void }) {
  return (
    <button type="button" className="mapthumb" onClick={onOpen} title="Switch to the Map view (M)">
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
        deathStar={state.deathStar}
        facilities={state.facilities}
      />
      <span className="mapthumb__cta">
        View map <kbd>M</kbd>
      </span>
    </button>
  );
}
