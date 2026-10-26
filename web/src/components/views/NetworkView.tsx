import { useMemo, useState } from "react";
import type { Axial, HexAction } from "../../api";
import { hexKey } from "../../hex";
import { useHotkeys } from "../../hotkeys";
import { useSettled } from "../../playback/useSettled";
import { findCorporation, hexActionsByKey, terrainByKey } from "../../selectors";
import { HexMap } from "../HexMap";
import { MapLegend } from "../MapLegend";
import { NetworkActions } from "../NetworkActions";
import { OperatingRail } from "../OperatingRail";
import { PlayerStrip } from "../PlayerStrip";
import type { ViewProps } from "./types";

/**
 * A president deciding what to build: the map takes the screen, the operating order runs down
 * the right with the current corporation's options. Each corporation turn and network action
 * starts with no hex picked and no other network in focus.
 */
export function NetworkView({ state, board, interactive, busy, keyboard, changedHexes, replayStep, onAct }: ViewProps) {
  const [explicitFocus, setExplicitFocus] = useState<string | null>(null);
  const [selectedHex, setSelectedHex] = useState<Axial | null>(null);
  const [preview, setPreview] = useState<HexAction | null>(null);
  // Reset the selection when the turn moves on, without remounting the map (which would cut short any animation).
  const turn = `${state.roundLabel}:${state.currentCorporation}:${state.networkActionsTaken}`;
  const [selectionTurn, setSelectionTurn] = useState(turn);
  if (turn !== selectionTurn) {
    setSelectionTurn(turn);
    setExplicitFocus(null);
    setSelectedHex(null);
    setPreview(null);
  }
  const focusCorp = explicitFocus ?? state.currentCorporation;
  // A replayed build draws in even when this view has just mounted for it: the map shows the
  // tiles from before the move for a frame, then the new ones.
  const tiles = useSettled(replayStep ? replayStep.before.tiles : state.tiles, state.tiles);
  const actingCorp = findCorporation(state, state.currentCorporation);
  const hexActions = useMemo(() => hexActionsByKey(state.legalActions), [state.legalActions]);
  const terrain = useMemo(() => terrainByKey(state.terrain), [state.terrain]);
  const actionableHexes = useMemo(
    () => (interactive ? new Set(hexActions.keys()) : new Set<string>()),
    [hexActions, interactive],
  );

  useHotkeys(
    {
      escape: () => {
        if (selectedHex === null && explicitFocus === null) return false;
        setSelectedHex(null);
        setExplicitFocus(null);
      },
    },
    keyboard,
  );

  function clickHex(hex: Axial) {
    setSelectedHex((current) => (current && hexKey(current) === hexKey(hex) ? null : hex));
    // Clicking a hex is about the acting corporation, so drop any other focus.
    setExplicitFocus(null);
  }

  function toggleFocus(corpId: string) {
    setExplicitFocus((current) => (current === corpId || corpId === state.currentCorporation ? null : corpId));
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
            tiles={tiles}
            terrain={terrain}
            nebulaChartSurcharge={state.config.nebulaChartSurcharge}
            corporations={state.corporations}
            focusCorp={focusCorp}
            actionableHexes={actionableHexes}
            selectedHex={selectedHex}
            preview={preview}
            changedHexes={changedHexes}
            onHexClick={clickHex}
            deathStar={state.deathStar}
          />
        </div>
        <MapLegend state={state} focusCorp={focusCorp} />
      </section>

      <OperatingRail state={state} focusCorp={focusCorp} onFocus={toggleFocus}>
        {actingCorp && (
          <NetworkActions
            state={state}
            corp={actingCorp}
            selectedHex={selectedHex}
            interactive={interactive}
            busy={busy}
            keyboard={keyboard}
            onSelectHex={setSelectedHex}
            onPreview={setPreview}
            onAct={onAct}
          />
        )}
      </OperatingRail>
    </div>
  );
}
