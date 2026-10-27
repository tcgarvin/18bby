import { useEffect, useState } from "react";
import type { Action, Board, GameState, LogEntry } from "../api";
import { ApiError, isHexAction, submitAction, undoAction } from "../api";
import { hexKey } from "../hex";
import { useHotkeys } from "../hotkeys";
import { newLogEntries } from "../logdiff";
import { FlightLayer } from "../playback/FlightLayer";
import { PhaseBanner, ReplayBar } from "../playback/ReplayBar";
import { StepEffects } from "../playback/StepEffects";
import { playbackSteps } from "../playback/frames";
import { usePlayback } from "../playback/usePlayback";
import { corpColor } from "../selectors";
import { changedFacilityHexes } from "../facilities";
import { changedHexes } from "../tilediff";
import { DeathStarBar } from "./DeathStar";
import { LogPanel } from "./LogPanel";
import { MapOverlay } from "./MapOverlay";
import { Overlay } from "./Overlay";
import { RecentMoves } from "./RecentMoves";
import { StockMarket } from "./StockMarket";
import { TopBar } from "./TopBar";
import { DividendView } from "./views/DividendView";
import { FacilityView } from "./views/FacilityView";
import { FleetView } from "./views/FleetView";
import { GameOverView } from "./views/GameOverView";
import { NetworkView } from "./views/NetworkView";
import { StockRoundView } from "./views/StockRoundView";
import type { OverlayKind, ViewProps } from "./views/types";
import "./GameScreen.css";

interface GameScreenProps {
  gameId: string;
  board: Board;
  initialState: GameState;
  onLeave: () => void;
}

const NO_CHANGES = new Map<string, string[]>();

/** Which overlays each phase offers: everything except what its view already features. */
const OVERLAYS: Record<GameState["phase"], OverlayKind[]> = {
  stock: ["map", "log"],
  network: ["market", "log"],
  fleet: ["market", "log"],
  dividend: ["map", "market", "log"],
  game_over: ["map", "market", "log"],
};

/** Log lines played automatically in the request that produced `state` (bots, forced moves). */
function automaticEntries(state: GameState): LogEntry[] {
  return state.log.filter((entry) => entry.seq >= state.automaticLogStart);
}

/**
 * Empire log lines that the player's own move caused (a seizure at the end of the round it ended,
 * say), which happen whether or not anyone else moved after it.
 */
function empireConsequences(before: GameState, after: GameState): LogEntry[] {
  const own = (after.moves ?? []).filter((move) => !move.automatic);
  if (!playbackSteps(before, after).some((step) => step.kind.kind === "empire" && !step.frame?.automatic)) return [];
  return own.flatMap((move) => move.log.filter((entry) => entry.actor === "Empire"));
}

/** A new game's opening bot moves: there is no earlier state to replay them from, so list them. */
function openingMoves(state: GameState): LogEntry[] {
  return (state.moves ?? []).some((move) => move.automatic) ? automaticEntries(state) : [];
}

/** The server state before and after the last batch of automatic moves, to watch again. */
interface Replayable {
  before: GameState;
  after: GameState;
}

/**
 * One game: owns the server state, sends actions and undo, and keeps errors and the "since your
 * move" summary. What it draws comes from `display`, which the replay engine holds on each
 * opponent move in turn while it animates `state.moves`; the phase view is chosen from
 * `display.phase` alone, and controls are offered only when `display` is the latest state.
 *
 * The "since your move" ribbon and the map's change outlines summarise a batch once it has
 * played, so they are hidden during the replay itself (whose captions say the same things).
 */
export function GameScreen({ gameId, board, initialState, onLeave }: GameScreenProps) {
  const [state, setState] = useState(initialState);
  const [fresh, setFresh] = useState<LogEntry[]>([]);
  const [recent, setRecent] = useState<LogEntry[]>(() => openingMoves(initialState));
  const [lastBatch, setLastBatch] = useState<Replayable | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [overlay, setOverlay] = useState<OverlayKind | null>(null);
  /** Hexes changed by bots or forced moves since the last submitted action. */
  const [changed, setChanged] = useState<Map<string, string[]>>(new Map());

  const playback = usePlayback(state, board.planets);
  const display: GameState = playback.display;
  const replaying = playback.playing;
  const interactive = !replaying && display.waitingOnHuman && display.phase !== "game_over";
  const step = playback.current;
  const actorColor = step && step.frame?.corporation ? corpColor(display, step.frame.corporation) : "";

  const available = OVERLAYS[display.phase];
  const shownOverlay = overlay !== null && available.includes(overlay) ? overlay : null;
  // An overlay belongs to the view it was opened over; a replay stepping through phases must not
  // keep hiding and reviving it, or leave it covering the next turn.
  useEffect(() => setOverlay(null), [display.phase]);

  async function send(request: () => Promise<GameState>, onDone: (next: GameState) => void) {
    setBusy(true);
    setError(null);
    try {
      const next = await request();
      // The server has saved the move: show its state first, so a failure while preparing the
      // replay cannot leave the screen behind the game.
      setState(next);
      onDone(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `Could not reach the server: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  function act(action: Action) {
    void send(
      () => submitAction(gameId, action),
      (next) => {
        setFresh(newLogEntries(state.log, next.log));
        const automatic = [...empireConsequences(state, next), ...automaticEntries(next)];
        // A move nobody answered (the first of two network actions) keeps the previous summary.
        if (automatic.length === 0) return;
        playback.enqueue(state, next);
        setLastBatch({ before: state, after: next });
        setRecent(automatic);
        const hexes = new Map([
          ...changedHexes(state.tiles, next.tiles),
          ...changedFacilityHexes(state.facilities, next.facilities),
        ]);
        if (isHexAction(action)) hexes.delete(hexKey(action.hex));
        if (action.type === "build_facility") {
          // Your own facility is no news; one a bot built on the same planet still is.
          const key = hexKey(action.planet);
          const others = (hexes.get(key) ?? []).filter((corp) => corp !== state.currentCorporation);
          if (others.length > 0) hexes.set(key, others);
          else hexes.delete(key);
        }
        setChanged(hexes);
      },
    );
  }

  function undo() {
    void send(
      () => undoAction(gameId),
      () => {
        setFresh([]);
        setRecent([]);
        setLastBatch(null);
        setChanged(new Map());
      },
    );
  }

  function dismissRecent() {
    setRecent([]);
    setLastBatch(null);
    setChanged(new Map());
  }

  // Watch again only while the batch's result is still the game on screen.
  const rewatch = lastBatch !== null && lastBatch.after === state ? lastBatch : null;

  function toggleOverlay(kind: OverlayKind) {
    if (!available.includes(kind)) return false;
    setOverlay((current) => (current === kind ? null : kind));
  }

  const canUndo = state.canUndo && !busy && !replaying;
  useHotkeys(
    {
      "mod+z": () => (canUndo ? undo() : false),
      u: () => (canUndo ? undo() : false),
      m: () => toggleOverlay("map"),
      k: () => toggleOverlay("market"),
      l: () => toggleOverlay("log"),
      escape: () => (shownOverlay ? setOverlay(null) : false),
    },
    !replaying,
  );
  // While a replay runs, Space and Esc skip it (Esc closes an open overlay first) and every other
  // shortcut is off.
  useHotkeys(
    { " ": () => playback.skip(), escape: () => (shownOverlay ? setOverlay(null) : playback.skip()) },
    replaying,
  );

  const viewProps: ViewProps = {
    state: display,
    board,
    interactive,
    busy,
    keyboard: shownOverlay === null && !replaying,
    changedHexes: replaying ? NO_CHANGES : changed,
    replayStep: step,
    onAct: act,
    onOpen: (kind) => setOverlay(kind),
  };

  return (
    <FlightLayer>
      <div className="app app--game">
        <StepEffects step={step} durationMs={playback.durationMs} color={(id) => corpColor(display, id)} />
        <TopBar
          state={display}
          gameId={gameId}
          overlays={available}
          openOverlay={shownOverlay}
          onToggleOverlay={toggleOverlay}
          canUndo={canUndo}
          onUndo={undo}
          onLeave={onLeave}
        />
        {display.deathStar && <DeathStarBar deathStar={display.deathStar} over={display.phase === "game_over"} />}
        {recent.length > 0 && !replaying && (
          <RecentMoves
            state={display}
            entries={recent}
            mapChanged={changed.size > 0}
            speed={playback.speed}
            onSpeed={playback.setSpeed}
            onReplay={rewatch ? () => playback.enqueue(rewatch.before, rewatch.after) : null}
            onShowLog={() => setOverlay("log")}
            onDismiss={dismissRecent}
          />
        )}
        {error && (
          <div className="error error--bar" role="alert">
            <span>{error}</span>
            <button type="button" className="link" onClick={() => setError(null)}>
              dismiss
            </button>
          </div>
        )}

        <main className={`stage stage--${display.phase}${replaying ? " stage--replaying" : ""}`}>
          {/* The replay caption: the move being animated, with speed and Skip. */}
          <div className="caption-slot" aria-live="polite">
            {step && (
              <ReplayBar
                step={step}
                index={playback.index}
                total={playback.total}
                speed={playback.speed}
                color={actorColor}
                onSpeed={playback.setSpeed}
                onSkip={playback.skip}
              />
            )}
          </div>
          {step?.kind.kind === "phase" && <PhaseBanner title={step.caption} />}
          {display.phase === "stock" ? (
            <StockRoundView {...viewProps} />
          ) : display.phase === "network" ? (
            <NetworkView {...viewProps} />
          ) : display.phase === "fleet" ? (
            display.facilities ? (
              <FacilityView {...viewProps} />
            ) : (
              <FleetView {...viewProps} />
            )
          ) : display.phase === "dividend" ? (
            <DividendView {...viewProps} />
          ) : (
            <GameOverView {...viewProps} onNewGame={onLeave} />
          )}
        </main>

        {shownOverlay === "map" && (
          <MapOverlay
            state={display}
            board={board}
            changedHexes={replaying ? NO_CHANGES : changed}
            onClose={() => setOverlay(null)}
          />
        )}
        {shownOverlay === "market" && (
          <Overlay title="Stock market" wide fit onClose={() => setOverlay(null)}>
            <div className="overlay-market">
              <p className="muted overlay-market__hint">
                Paying moves right (two columns for a big payout), withholding left; selling moves down, a sold-out
                corporation moves up.
              </p>
              <StockMarket state={display} anchors={false} />
            </div>
          </Overlay>
        )}
        {shownOverlay === "log" && (
          <Overlay title="Game log" onClose={() => setOverlay(null)}>
            <LogPanel state={display} fresh={fresh} />
          </Overlay>
        )}
      </div>
    </FlightLayer>
  );
}
