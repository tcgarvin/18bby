import { useState } from "react";
import type { Action, Board, GameState, LogEntry } from "../api";
import { ApiError, isHexAction, submitAction, undoAction } from "../api";
import type { GameView } from "../gameView";
import { availableViews, browseBanner, followSelection, initialSelection, liveView, shownView, viewForKey } from "../gameView";
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
import { Overlay } from "./Overlay";
import { RecentMoves } from "./RecentMoves";
import { TopBar } from "./TopBar";
import { DividendView } from "./views/DividendView";
import { FacilityView } from "./views/FacilityView";
import { FleetView } from "./views/FleetView";
import { GameOverView } from "./views/GameOverView";
import { MapBrowseView } from "./views/MapBrowseView";
import { NetworkView } from "./views/NetworkView";
import { StockRoundView } from "./views/StockRoundView";
import { SurrenderView } from "./views/SurrenderView";
import type { ViewProps } from "./views/types";
import "./GameScreen.css";

interface GameScreenProps {
  gameId: string;
  board: Board;
  initialState: GameState;
  onLeave: () => void;
}

const NO_CHANGES = new Map<string, string[]>();
const VIEW_KEYS = ["v", "m", "s", "k"] as const;

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
 * opponent move in turn while it animates `state.moves`.
 *
 * The screen has two views the player can flip between, Shares and Map (`gameView.ts`); the one
 * for `display.phase` is live, the other is browsed read-only. Only one view is mounted at a
 * time, so each animation anchor appears once. A phase change or the start of a replay snaps
 * back to the live view in the same render, before the replay's effects look for their anchors.
 * Controls are offered only on the live view, when `display` is the latest state and a human is
 * to move.
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
  const [logOpen, setLogOpen] = useState(false);
  /** Hexes changed by bots or forced moves since the last submitted action. */
  const [changed, setChanged] = useState<Map<string, string[]>>(new Map());

  const playback = usePlayback(state, board.planets);
  const display: GameState = playback.display;
  const replaying = playback.playing;
  const step = playback.current;
  const actorColor = step && step.frame?.corporation ? corpColor(display, step.frame.corporation) : "";

  const [selection, setSelection] = useState(() => initialSelection(initialState.phase, false));
  /** A manual switch fades the new view in; snaps (phase changes, replays) are immediate. */
  const [entering, setEntering] = useState(false);
  // Snap back during render, not in an effect, so a replay's first step never mounts on the
  // browsed view and its effects find the live view's anchors.
  const followed = followSelection(selection, display.phase, replaying);
  if (followed !== selection) {
    setSelection(followed);
    if (followed.view === null) setEntering(false);
  }
  const live = liveView(display.phase);
  const shown = shownView(followed);
  const browsing = shown !== live;
  const interactive = !browsing && !replaying && display.waitingOnHuman && display.phase !== "game_over";
  const banner = browseBanner(display.phase, shown);

  function selectView(view: GameView) {
    if (view === shown) return;
    setSelection({ ...followed, view: view === live ? null : view });
    setEntering(true);
  }

  function selectViewByKey(key: string) {
    const next = viewForKey(key, shown, display.phase);
    if (next === null || next === shown) return false;
    selectView(next);
  }

  // View shortcuts work during a replay too, but not while the log is open.
  const viewKeys = logOpen ? {} : Object.fromEntries(VIEW_KEYS.map((key) => [key, () => selectViewByKey(key)]));

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

  const canUndo = state.canUndo && !busy && !replaying;
  useHotkeys(
    {
      ...viewKeys,
      "mod+z": () => (canUndo ? undo() : false),
      u: () => (canUndo ? undo() : false),
      l: () => setLogOpen((open) => !open),
      escape: () => (logOpen ? setLogOpen(false) : false),
    },
    !replaying,
  );
  // While a replay runs, Space and Esc skip it (Esc closes the log first) and the view shortcuts
  // still switch views; every other shortcut is off.
  useHotkeys(
    { ...viewKeys, " ": () => playback.skip(), escape: () => (logOpen ? setLogOpen(false) : playback.skip()) },
    replaying,
  );

  const viewProps: ViewProps = {
    state: display,
    board,
    interactive,
    browsing,
    busy,
    keyboard: !logOpen && !replaying,
    changedHexes: replaying ? NO_CHANGES : changed,
    replayStep: step,
    onAct: act,
    onView: selectView,
  };

  function phaseView() {
    if (shown === "shares") return <StockRoundView {...viewProps} />;
    if (shown === "results") return <GameOverView {...viewProps} onNewGame={onLeave} />;
    switch (display.phase) {
      case "network":
        return <NetworkView {...viewProps} />;
      case "fleet":
        return display.facilities ? <FacilityView {...viewProps} /> : <FleetView {...viewProps} />;
      case "dividend":
        return <DividendView {...viewProps} />;
      case "surrender":
        return <SurrenderView {...viewProps} />;
      default:
        return <MapBrowseView {...viewProps} />;
    }
  }

  const stageClass = [
    "stage",
    `stage--${display.phase}`,
    `stage--view-${shown}`,
    replaying ? "stage--replaying" : "",
    entering ? "stage--entering" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <FlightLayer>
      <div className="app app--game">
        <StepEffects step={step} durationMs={playback.durationMs} color={(id) => corpColor(display, id)} />
        <TopBar
          state={display}
          gameId={gameId}
          views={availableViews(display.phase)}
          shownView={shown}
          liveView={display.phase === "game_over" ? null : live}
          onView={selectView}
          logOpen={logOpen}
          onToggleLog={() => setLogOpen((open) => !open)}
          canUndo={canUndo}
          onUndo={undo}
          onLeave={onLeave}
        />
        {display.deathStar && (
          <DeathStarBar deathStar={display.deathStar} over={display.phase === "game_over"} chainRules={display.config.chainRules} />
        )}
        {recent.length > 0 && !replaying && (
          <RecentMoves
            state={display}
            entries={recent}
            mapChanged={changed.size > 0}
            speed={playback.speed}
            onSpeed={playback.setSpeed}
            onReplay={rewatch ? () => playback.enqueue(rewatch.before, rewatch.after) : null}
            onShowLog={() => setLogOpen(true)}
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

        <main className={stageClass}>
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
          {banner && (
            <div className="browse-banner" role="status">
              <span className="browse-banner__text">{banner.text}</span>
              <button type="button" className="btn btn--small browse-banner__back" onClick={() => selectView(live)}>
                {banner.back}
              </button>
            </div>
          )}
          {phaseView()}
        </main>

        {logOpen && (
          <Overlay title="Game log" onClose={() => setLogOpen(false)}>
            <LogPanel state={display} fresh={fresh} />
          </Overlay>
        )}
      </div>
    </FlightLayer>
  );
}
