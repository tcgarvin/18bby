import { useMemo, useState } from "react";
import { findCorporation, terrainByKey } from "../../selectors";
import { FleetActions } from "../FleetActions";
import { HexMap } from "../HexMap";
import { MapLegend } from "../MapLegend";
import { OperatingRail } from "../OperatingRail";
import { PlayerStrip } from "../PlayerStrip";
import type { ViewProps } from "./types";

const NO_HEXES = new Set<string>();

/**
 * A president buying fleets (Death Star rules): the map with the corporation's network and the
 * pairs its fleets run, and the operating order with the fleet step in the current entry.
 */
export function FleetView({ state, board, interactive, busy, keyboard, changedHexes, onAct }: ViewProps) {
  const [explicitFocus, setExplicitFocus] = useState<string | null>(null);
  const turn = `${state.roundLabel}:${state.currentCorporation}`;
  const [focusTurn, setFocusTurn] = useState(turn);
  if (turn !== focusTurn) {
    setFocusTurn(turn);
    setExplicitFocus(null);
  }
  const focusCorp = explicitFocus ?? state.currentCorporation;
  const actingCorp = findCorporation(state, state.currentCorporation);
  const terrain = useMemo(() => terrainByKey(state.terrain), [state.terrain]);

  return (
    <div className="view view--operating">
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
            focusCorp={focusCorp}
            actionableHexes={NO_HEXES}
            selectedHex={null}
            preview={null}
            changedHexes={changedHexes}
            onHexClick={() => undefined}
            deathStar={state.deathStar}
          />
        </div>
        <MapLegend state={state} focusCorp={focusCorp} />
      </section>

      <OperatingRail
        state={state}
        focusCorp={focusCorp}
        onFocus={(id) => setExplicitFocus((current) => (current === id || id === state.currentCorporation ? null : id))}
      >
        {actingCorp && (
          <FleetActions
            state={state}
            corp={actingCorp}
            interactive={interactive}
            busy={busy}
            keyboard={keyboard}
            onAct={onAct}
          />
        )}
      </OperatingRail>
    </div>
  );
}
