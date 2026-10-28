import { useMemo, useState } from "react";
import { useHotkeys } from "../../hotkeys";
import { terrainByKey } from "../../selectors";
import { HexMap } from "../HexMap";
import { MapLegend } from "../MapLegend";
import { OperatingRail } from "../OperatingRail";
import { PlayerStrip } from "../PlayerStrip";
import type { ViewProps } from "./types";

const NO_HEXES = new Set<string>();

/**
 * The Map browsed outside an operating round (during a stock round, or at game over): the whole
 * map with every corporation down the side, read-only. Every network shows until a corporation
 * is picked in the list; picking it again shows them all.
 */
export function MapBrowseView({ state, board, keyboard, changedHexes }: ViewProps) {
  const [focus, setFocus] = useState<string | null>(null);
  const terrain = useMemo(() => terrainByKey(state.terrain), [state.terrain]);

  useHotkeys({ escape: () => (focus === null ? false : setFocus(null)) }, keyboard);

  return (
    <div className="view view--operating view--map-browse">
      <section className="panel mapstage">
        <div className="mapstage__top">
          <PlayerStrip state={state} compact />
        </div>
        <div className="mapstage__map">
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
      </section>

      <OperatingRail
        state={state}
        focusCorp={focus}
        mode="corporations"
        onFocus={(id) => setFocus((current) => (current === id ? null : id))}
      />
    </div>
  );
}
