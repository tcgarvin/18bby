import { useMemo, useState } from "react";
import type { Axial, BuildFacilityAction } from "../../api";
import { buildsByPlanet } from "../../facilities";
import { hexKey } from "../../hex";
import { useHotkeys } from "../../hotkeys";
import { useSettled } from "../../playback/useSettled";
import { findCorporation, terrainByKey } from "../../selectors";
import { FacilityActions } from "../FacilityActions";
import { HexMap } from "../HexMap";
import { MapLegend } from "../MapLegend";
import { OperatingRail } from "../OperatingRail";
import { PlayerStrip } from "../PlayerStrip";
import type { ViewProps } from "./types";

/**
 * A president building facilities (facility rules): the map with the planets it may build on,
 * and the operating order with the facility step in the current entry. Picking a planet, on the
 * map or in the rail, lists where its new exit can go; hovering one previews it on the map. Each
 * build and each corporation turn starts with no planet picked and no other network in focus.
 */
export function FacilityView({ state, board, interactive, busy, keyboard, changedHexes, replayStep, onAct }: ViewProps) {
  const [explicitFocus, setExplicitFocus] = useState<string | null>(null);
  const [selected, setSelected] = useState<Axial | null>(null);
  const [preview, setPreview] = useState<BuildFacilityAction | null>(null);
  const actingCorp = findCorporation(state, state.currentCorporation);
  const turn = `${state.roundLabel}:${state.currentCorporation}:${actingCorp?.fleets ?? 0}`;
  const [selectionTurn, setSelectionTurn] = useState(turn);
  if (turn !== selectionTurn) {
    setSelectionTurn(turn);
    setExplicitFocus(null);
    setSelected(null);
    setPreview(null);
  }
  const focusCorp = explicitFocus ?? state.currentCorporation;
  // A replayed build pops in even when this view has just mounted for it.
  const facilities = useSettled(replayStep ? replayStep.before.facilities : state.facilities, state.facilities);
  const terrain = useMemo(() => terrainByKey(state.terrain), [state.terrain]);
  const builds = useMemo(() => buildsByPlanet(state), [state]);
  const actionableHexes = useMemo(() => (interactive ? new Set(builds.keys()) : new Set<string>()), [builds, interactive]);

  useHotkeys(
    {
      escape: () => {
        if (selected === null && explicitFocus === null) return false;
        selectPlanet(null);
        setExplicitFocus(null);
      },
    },
    keyboard,
  );

  function selectPlanet(hex: Axial | null) {
    setSelected(hex);
    setPreview(null);
  }

  function clickHex(hex: Axial) {
    selectPlanet(selected && hexKey(selected) === hexKey(hex) ? null : hex);
    // Picking a planet is about the acting corporation, so drop any other focus.
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
            actionableHexes={actionableHexes}
            selectedHex={selected}
            preview={null}
            changedHexes={changedHexes}
            onHexClick={clickHex}
            deathStar={state.deathStar}
            facilities={facilities}
            facilityPreview={interactive ? preview : null}
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
          <FacilityActions
            state={state}
            corp={actingCorp}
            selectedPlanet={selected}
            interactive={interactive}
            busy={busy}
            keyboard={keyboard}
            onSelectPlanet={selectPlanet}
            onPreview={setPreview}
            onAct={onAct}
          />
        )}
      </OperatingRail>
    </div>
  );
}
