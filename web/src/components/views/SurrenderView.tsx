import { useMemo, useState } from "react";
import type { Axial } from "../../api";
import { hexKey } from "../../hex";
import { useHotkeys } from "../../hotkeys";
import { terrainByKey } from "../../selectors";
import { HexMap } from "../HexMap";
import { MapLegend } from "../MapLegend";
import { OperatingRail } from "../OperatingRail";
import { PlayerStrip } from "../PlayerStrip";
import { SurrenderActions } from "../SurrenderActions";
import type { ViewProps } from "./types";

/**
 * A seizure under the chain rules: the map on the choosing corporation's network, its facilities'
 * planets highlighted, and down the side the corporations the Empire asked, in the order they
 * choose, with the chooser's options. Picking a planet on the map marks its option; hovering an
 * option shows its planet.
 */
export function SurrenderView({ state, board, interactive, busy, keyboard, changedHexes, onAct }: ViewProps) {
  const [explicitFocus, setExplicitFocus] = useState<string | null>(null);
  const [selected, setSelected] = useState<Axial | null>(null);
  const [highlight, setHighlight] = useState<Axial | null>(null);
  const turn = `${state.roundLabel}:${state.currentCorporation}`;
  const [selectionTurn, setSelectionTurn] = useState(turn);
  if (turn !== selectionTurn) {
    setSelectionTurn(turn);
    setExplicitFocus(null);
    setSelected(null);
    setHighlight(null);
  }
  const focusCorp = explicitFocus ?? state.currentCorporation;
  const terrain = useMemo(() => terrainByKey(state.terrain), [state.terrain]);
  const options = state.facilities?.surrenderOptions ?? [];
  const optionHexes = useMemo(() => new Set(options.map((option) => hexKey(option.action.planet))), [options]);

  useHotkeys(
    {
      escape: () => {
        if (selected === null && explicitFocus === null) return false;
        setSelected(null);
        setExplicitFocus(null);
      },
    },
    keyboard,
  );

  function clickHex(hex: Axial) {
    if (!optionHexes.has(hexKey(hex))) return;
    setSelected(selected && hexKey(selected) === hexKey(hex) ? null : hex);
    setExplicitFocus(null);
  }

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
            actionableHexes={optionHexes}
            selectedHex={highlight ?? selected}
            preview={null}
            changedHexes={changedHexes}
            onHexClick={clickHex}
            deathStar={state.deathStar}
            facilities={state.facilities}
          />
        </div>
        <MapLegend state={state} focusCorp={focusCorp} />
      </section>

      <OperatingRail
        state={state}
        focusCorp={focusCorp}
        onFocus={(id) => setExplicitFocus((current) => (current === id || id === state.currentCorporation ? null : id))}
      >
        <SurrenderActions
          state={state}
          selectedPlanet={selected}
          interactive={interactive}
          busy={busy}
          keyboard={keyboard}
          onHighlight={setHighlight}
          onAct={onAct}
        />
      </OperatingRail>
    </div>
  );
}
