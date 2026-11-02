import { useEffect, useMemo, useState } from "react";
import type { Action, Axial, Board, BuildFacilityAction, CorporationState, DividendAction, GameState, HexAction } from "../api";
import { fitViewBox, HexMap } from "../components/HexMap";
import { FacilityActions } from "../components/FacilityActions";
import { TilePreview } from "../components/TilePreview";
import { nextSeizure } from "../deathstar";
import { buildsByPlanet, laneArrivals } from "../facilities";
import { hexKey } from "../hex";
import { useFlight } from "../playback/FlightLayer";
import { SpeedPicker } from "../playback/ReplayBar";
import { prefersReducedMotion } from "../playback/timing";
import type { Playback } from "../playback/usePlayback";
import { useSettled } from "../playback/useSettled";
import { Ticker } from "../playback/Ticker";
import { corpColor, dividendSplit, findCorporation, hexActionsByKey, playerName, terrainByKey } from "../selectors";
import { selectionHexes, stepHexes, turnHexes } from "./camera";
import "./phone.css";

/** How long the map takes to reframe on your own turn. */
const TURN_GLIDE_MS = 300;

interface PhoneGameProps {
  /** The state to draw: an intermediate one while a replay runs. */
  state: GameState;
  board: Board;
  playback: Playback;
  interactive: boolean;
  busy: boolean;
  changedHexes: Map<string, string[]>;
  canUndo: boolean;
  error: string | null;
  onAct: (action: Action) => void;
  onUndo: () => void;
  onLeave: () => void;
  onDismissError: () => void;
}

/**
 * The phone layout of one game (prototype): a header, the map framed on what the turn needs, and
 * a sheet with the turn's choices. While opponents' moves replay, strips of players and
 * corporations give the replay's tokens somewhere to land, and the controls replace the sheet. Its
 * elements carry the same data-* anchors as the desktop's, so the replay's effects are the same.
 */
export function PhoneGame(props: PhoneGameProps) {
  const { state, board, playback, interactive, busy, changedHexes, canUndo, error, onAct, onUndo, onLeave, onDismissError } = props;
  const flight = useFlight();
  const step = playback.current;
  const replaying = playback.playing;

  const [selectedHex, setSelectedHex] = useState<Axial | null>(null);
  const [preview, setPreview] = useState<HexAction | null>(null);
  const [selectedPlanet, setSelectedPlanet] = useState<Axial | null>(null);
  const [facilityPreview, setFacilityPreview] = useState<BuildFacilityAction | null>(null);
  const actingCorp = findCorporation(state, step ? step.frame?.corporation ?? "" : state.currentCorporation);
  // Each decision starts with nothing picked.
  const decision = `${state.roundLabel}:${state.phase}:${state.currentCorporation}:${state.networkActionsTaken}:${actingCorp?.fleets ?? 0}:${replaying}`;
  const [selectionDecision, setSelectionDecision] = useState(decision);
  if (decision !== selectionDecision) {
    setSelectionDecision(decision);
    setSelectedHex(null);
    setPreview(null);
    setSelectedPlanet(null);
    setFacilityPreview(null);
  }

  const hexActions = useMemo(() => hexActionsByKey(state.legalActions), [state.legalActions]);
  const builds = useMemo(() => buildsByPlanet(state), [state]);
  const terrain = useMemo(() => terrainByKey(state.terrain), [state.terrain]);
  const actionableHexes = useMemo(() => {
    if (!interactive) return new Set<string>();
    if (state.phase === "network") return new Set(hexActions.keys());
    if (state.phase === "fleet") return new Set(builds.keys());
    return new Set<string>();
  }, [interactive, state.phase, hexActions, builds]);

  // The camera: a replay step's frame, or the decision's, or wherever it last was.
  const wanted = useMemo((): Axial[] | null => {
    if (step) return stepHexes(step, board);
    const targets = board.hexes.filter((hex) => actionableHexes.has(hexKey(hex)));
    const turn = turnHexes(state, board, targets);
    return selectedHex ? selectionHexes(selectedHex, turn) : selectedPlanet ? selectionHexes(selectedPlanet, turn) : turn;
  }, [step, board, state, actionableHexes, selectedHex, selectedPlanet]);
  const [camera, setCamera] = useState<Axial[]>(() => wanted ?? board.hexes);
  if (wanted !== null && wanted.length > 0 && fitViewBox(wanted) !== fitViewBox(camera)) setCamera(wanted);

  // A replayed build draws in once the camera has arrived.
  const tiles = useSettled(step ? step.before.tiles : state.tiles, state.tiles, playback.leadMs);
  const facilities = useSettled(step ? step.before.facilities : state.facilities, state.facilities, playback.leadMs);

  // A phone gets put away mid-replay; the replay waits, and stays paused until asked to go on.
  useEffect(() => {
    const onVisibility = () => {
      if (document.hidden && playback.playing && !playback.paused) {
        playback.pause();
        flight.pause();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [playback, flight]);

  function togglePause() {
    if (playback.paused) {
      playback.resume();
      flight.resume();
    } else {
      playback.pause();
      flight.pause();
    }
  }

  function clickHex(hex: Axial) {
    if (state.phase === "fleet") {
      setSelectedPlanet((current) => (current && hexKey(current) === hexKey(hex) ? null : hex));
      setFacilityPreview(null);
      return;
    }
    const same = selectedHex !== null && hexKey(selectedHex) === hexKey(hex);
    setSelectedHex(same ? null : hex);
    setPreview(same ? null : (hexActions.get(hexKey(hex))?.[0] ?? null));
  }

  const glideMs = prefersReducedMotion() ? 0 : replaying ? playback.leadMs : TURN_GLIDE_MS;

  return (
    <div className={`phone${replaying ? " phone--replaying" : ""}`}>
      <PhoneHeader state={state} corp={actingCorp} step={step} canUndo={!replaying && canUndo} onUndo={onUndo} onLeave={onLeave} />
      {replaying && <Strips state={state} corp={actingCorp} />}
      {error && (
        <button type="button" className="phone__error" role="alert" onClick={onDismissError}>
          {error} (tap to dismiss)
        </button>
      )}
      <div className="phone__map">
        <HexMap
          board={board}
          tiles={tiles}
          terrain={terrain}
          nebulaChartSurcharge={state.config.nebulaChartSurcharge}
          corporations={state.corporations}
          focusCorp={actingCorp?.id ?? null}
          actionableHexes={actionableHexes}
          selectedHex={selectedHex ?? selectedPlanet}
          preview={interactive ? preview : null}
          changedHexes={changedHexes}
          onHexClick={clickHex}
          fitHexes={camera}
          glideMs={glideMs}
          deathStar={state.deathStar}
          facilities={facilities}
          facilityPreview={interactive ? facilityPreview : null}
          viewToggle={false}
        />
        {step?.kind.kind === "phase" && (
          <div className="phone__banner" role="status">
            <span key={step.caption}>{step.caption}</span>
          </div>
        )}
      </div>

      {replaying ? (
        <ReplayControls playback={playback} onTogglePause={togglePause} />
      ) : (
        actingCorp && (
          <div className="phone__sheet">
            {state.phase === "network" && (
              <NetworkSheet
                state={state}
                corp={actingCorp}
                selectedHex={selectedHex}
                preview={preview}
                interactive={interactive}
                busy={busy}
                onPreview={setPreview}
                onClose={() => {
                  setSelectedHex(null);
                  setPreview(null);
                }}
                onAct={onAct}
              />
            )}
            {state.phase === "fleet" && (
              <div className="phone__scroll">
                <FacilityActions
                  state={state}
                  corp={actingCorp}
                  selectedPlanet={selectedPlanet}
                  interactive={interactive}
                  busy={busy}
                  keyboard={false}
                  onSelectPlanet={setSelectedPlanet}
                  onPreview={setFacilityPreview}
                  onAct={onAct}
                />
              </div>
            )}
            {state.phase === "dividend" && <DividendSheet state={state} corp={actingCorp} interactive={interactive} busy={busy} onAct={onAct} />}
          </div>
        )
      )}
    </div>
  );
}

function phaseTitle(state: GameState): string {
  if (state.phase === "network") return `Network ${Math.min(state.networkActionsTaken + 1, state.config.networkActionsPerTurn)} of ${state.config.networkActionsPerTurn}`;
  if (state.phase === "fleet") return "Facilities";
  if (state.phase === "dividend") return "Dividend";
  return "";
}

interface PhoneHeaderProps {
  state: GameState;
  corp: CorporationState | null;
  step: Playback["current"];
  canUndo: boolean;
  onUndo: () => void;
  onLeave: () => void;
}

/** Who is acting and how the game stands. Anchors: data-treasury-for, data-death-star-track, data-fleet-supply. */
function PhoneHeader({ state, corp, step, canUndo, onUndo, onLeave }: PhoneHeaderProps) {
  const seizure = state.deathStar ? nextSeizure(state.deathStar) : null;
  const title = step ? (step.frame ? playerName(state, step.frame.actor) : "") : phaseTitle(state);
  return (
    <header className="phone__head">
      <div className="phone__who">
        <div className="phone__title">
          {corp && (
            <span className="phone__chip" style={{ background: corpColor(state, corp.id) }}>
              {corp.id}
            </span>
          )}
          <span className="phone__name">{title}</span>
        </div>
        <div className="phone__sub">
          <span>{state.roundLabel}</span>
          {state.deathStar && (
            <span data-death-star-track="">
              {seizure ? `seizure in ${seizure.cubesToGo}` : `${state.deathStar.cubes}/${state.deathStar.totalCubes} cubes`}
            </span>
          )}
          {state.deathStar && <span data-fleet-supply="">facility {state.deathStar.fleets.price}</span>}
        </div>
      </div>
      {corp && (
        <div className="phone__treasury" data-treasury-for={corp.id}>
          <small>Treasury</small>
          <b className="num">
            <Ticker value={corp.treasury} />
          </b>
        </div>
      )}
      {!step && (
        <div className="phone__actions">
          <button type="button" disabled={!canUndo} onClick={onUndo}>
            Undo
          </button>
          <button type="button" onClick={onLeave}>
            Exit
          </button>
        </div>
      )}
    </header>
  );
}

/** Where a replay's tokens land. Anchors: data-player-id, data-cash-for, data-corp-id, data-market-token. */
function Strips({ state, corp }: { state: GameState; corp: CorporationState | null }) {
  return (
    <div className="phone__strips">
      <ul className="phone__players" aria-label="Players">
        {state.players.map((player) => (
          <li key={player.id} data-player-id={player.id} className={player.isBot ? "" : "phone__me"}>
            <span className="phone__player-name">{player.name}</span>
            <span className="num phone__cash" data-cash-for={player.id}>
              <Ticker value={player.cash} />
            </span>
          </li>
        ))}
      </ul>
      <ul className="phone__corps" aria-label="Corporations">
        {state.corporations.map((c) => (
          <li
            key={c.id}
            data-corp-id={c.id}
            className={`${c.id === corp?.id ? "phone__corp--acting" : ""}${c.status === "unstarted" ? " phone__corp--unstarted" : ""}`}
          >
            <span className="phone__chip" style={{ background: corpColor(state, c.id) }}>
              {c.id}
            </span>
            <span className="num" data-market-token={c.id}>
              {c.status === "unstarted" ? "–" : <Ticker value={c.price} />}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ReplayControls({ playback, onTogglePause }: { playback: Playback; onTogglePause: () => void }) {
  const { current, index, total, speed, paused, setSpeed, skip } = playback;
  return (
    <div className="phone__replay">
      <div className="phone__caption" aria-live="polite">
        <span className="phone__count num">
          {index + 1}/{total}
        </span>
        <span key={index}>{current?.caption}</span>
      </div>
      <div className="phone__controls">
        <button type="button" onClick={onTogglePause}>
          {paused ? "Resume" : "Pause"}
        </button>
        <SpeedPicker speed={speed} onChange={setSpeed} />
        <button type="button" onClick={skip}>
          Skip
        </button>
      </div>
    </div>
  );
}

/** What an option adds to its hex, in a few characters. */
function optionLabel(action: HexAction): string {
  if (action.type === "chart") return action.exits.join("–");
  if (action.type === "upgrade") return `+${action.exit}`;
  return "Service";
}

function buildLabel(action: HexAction): string {
  if (action.type === "chart") return `Chart for ${action.cost}`;
  if (action.type === "upgrade") return `Add exit for ${action.cost}`;
  return `Extend service for ${action.cost}`;
}

interface NetworkSheetProps {
  state: GameState;
  corp: CorporationState;
  selectedHex: Axial | null;
  preview: HexAction | null;
  interactive: boolean;
  busy: boolean;
  onPreview: (action: HexAction) => void;
  onClose: () => void;
  onAct: (action: Action) => void;
}

/**
 * The network step. Tapping a hex opens its options; tapping an option shows it on the map, since
 * a phone has no hover to preview with; a separate button then builds it.
 */
function NetworkSheet({ state, corp, selectedHex, preview, interactive, busy, onPreview, onClose, onAct }: NetworkSheetProps) {
  const byKey = hexActionsByKey(state.legalActions);
  const terrain = terrainByKey(state.terrain);
  const noAction = state.legalActions.find((a) => a.type === "no_action");
  const options = interactive && selectedHex ? (byKey.get(hexKey(selectedHex)) ?? []) : [];
  const color = corpColor(state, corp.id);

  if (selectedHex && options.length > 0) {
    const tile = state.tiles.find((t) => hexKey(t.hex) === hexKey(selectedHex));
    const arrivals = preview ? laneArrivals(preview, state.facilities) : [];
    return (
      <div className="netsheet">
        <div className="netsheet__line">
          <strong>
            Hex ({selectedHex[0]}, {selectedHex[1]})
          </strong>
          <span>
            {tile ? `charted ${tile.exits.join("/")}` : "uncharted"}
            {terrain.get(hexKey(selectedHex)) === "nebula" ? " · nebula" : ""}
          </span>
        </div>
        <div className="netsheet__options" role="group" aria-label="Options for this hex">
          {options.map((action) => (
            <button
              type="button"
              key={JSON.stringify(action)}
              className="netsheet__option"
              aria-pressed={preview !== null && JSON.stringify(preview) === JSON.stringify(action)}
              onClick={() => onPreview(action)}
            >
              <TilePreview
                existing={action.type === "chart" ? [] : (tile?.exits ?? [])}
                added={action.type === "chart" ? action.exits : action.type === "upgrade" ? [action.exit] : []}
                color={color}
                size={44}
              />
              <span>{optionLabel(action)}</span>
            </button>
          ))}
        </div>
        <div className="netsheet__line netsheet__line--effect">
          <span className="netsheet__arrivals">
            {arrivals.length === 0
              ? "Reaches no planet yet"
              : arrivals.map((arrival) => (
                  <span key={arrival.planet} className={arrival.claims ? "" : "netsheet__dangles"}>
                    {arrival.claims ? `Claims ${arrival.planet}` : `Dangles at ${arrival.planet}`}
                  </span>
                ))}
          </span>
          {preview && (
            <span className="num">
              {corp.treasury} → {corp.treasury - preview.cost}
            </span>
          )}
        </div>
        <div className="netsheet__buttons">
          <button type="button" className="phone__button" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="phone__button phone__button--primary"
            disabled={busy || preview === null}
            onClick={() => preview && onAct(preview)}
          >
            {preview ? buildLabel(preview) : "Pick an option"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="netsheet">
      <div className="netsheet__line">
        <strong>{byKey.size > 0 ? "Tap a highlighted hex" : "Nothing to build"}</strong>
        {byKey.size > 0 && <span>{byKey.size} {byKey.size === 1 ? "hex" : "hexes"}</span>}
      </div>
      <div className="netsheet__line netsheet__costs num">
        Chart {state.config.chartCost} · Add exit {state.config.upgradeCost} · Service {state.config.serviceCost}
      </div>
      {interactive && noAction && (
        <button type="button" className="phone__button" disabled={busy} onClick={() => onAct(noAction)}>
          {state.networkActionsTaken > 0 ? "End network actions" : "No network action"}
        </button>
      )}
    </div>
  );
}

/** The dividend step: pay or keep what the corporation earned. A placeholder for the real screen. */
function DividendSheet({ state, corp, interactive, busy, onAct }: { state: GameState; corp: CorporationState; interactive: boolean; busy: boolean; onAct: (action: Action) => void }) {
  const choices = interactive ? state.legalActions.filter((a): a is DividendAction => a.type === "dividend") : [];
  const pay = choices.find((a) => a.choice === "pay");
  const withhold = choices.find((a) => a.choice === "withhold");
  const total = corp.revenue.total;
  const prices = corp.dividendPreview ?? { pay: corp.price, withhold: corp.price };
  const split = dividendSplit(state, corp, total);
  return (
    <div className="netsheet">
      <div className="netsheet__line">
        <strong>{corp.id} earned {total}</strong>
        <span className="num">price {corp.price}</span>
      </div>
      <div className="netsheet__buttons netsheet__buttons--even">
        <button type="button" className="phone__button phone__button--tall" disabled={busy || !pay} onClick={() => pay && onAct(pay)}>
          <b>Pay {total}</b>
          <small>
            {split.perShare} a share, price {prices.pay}
          </small>
        </button>
        <button type="button" className="phone__button phone__button--tall" disabled={busy || !withhold} onClick={() => withhold && onAct(withhold)}>
          <b>Withhold</b>
          <small>
            treasury {corp.treasury + total}, price {prices.withhold}
          </small>
        </button>
      </div>
    </div>
  );
}
