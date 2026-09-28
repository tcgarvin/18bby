import { useEffect, useMemo, useState } from "react";
import type { Action, Axial, Board, GameState, HexAction, LogEntry } from "../api";
import { ApiError, isHexAction, submitAction, undoAction } from "../api";
import { corporationColor } from "../colors";
import { hexKey } from "../hex";
import { useHotkeys } from "../hotkeys";
import { newLogEntries } from "../logdiff";
import { findCorporation, hexActionsByKey, playerName } from "../selectors";
import { changedHexes } from "../tilediff";
import { CorporationsPanel } from "./CorporationsPanel";
import { DividendActions } from "./DividendActions";
import { GameOver } from "./GameOver";
import { HexMap } from "./HexMap";
import { LogPanel, actorLabel } from "./LogPanel";
import { NetworkActions } from "./NetworkActions";
import { PlayersPanel } from "./PlayersPanel";
import { StockActions } from "./StockActions";
import { StockMarket } from "./StockMarket";

interface GameScreenProps {
  gameId: string;
  board: Board;
  initialState: GameState;
  onLeave: () => void;
}

const PHASE_NAMES: Record<GameState["phase"], string> = {
  stock: "Stock round",
  network: "Operating · network",
  dividend: "Operating · dividend",
  game_over: "Game over",
};

export function GameScreen({ gameId, board, initialState, onLeave }: GameScreenProps) {
  const [state, setState] = useState(initialState);
  const [fresh, setFresh] = useState<LogEntry[]>([]);
  const [recent, setRecent] = useState<LogEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [explicitFocus, setExplicitFocus] = useState<string | null>(null);
  const [selectedHex, setSelectedHex] = useState<Axial | null>(null);
  const [preview, setPreview] = useState<HexAction | null>(null);
  /** Hexes changed by bots or forced moves since the last submitted action. */
  const [changed, setChanged] = useState<Map<string, string[]>>(new Map());

  // A new operating corporation or phase starts from a clean selection.
  const turnKey = `${state.phase}:${state.roundLabel}:${state.currentCorporation ?? state.currentPlayer ?? ""}`;
  useEffect(() => {
    setExplicitFocus(null);
    setSelectedHex(null);
    setPreview(null);
  }, [turnKey]);

  const focusCorp = explicitFocus ?? state.currentCorporation;
  const actingCorp = findCorporation(state, state.currentCorporation);
  const hexActions = useMemo(() => hexActionsByKey(state.legalActions), [state.legalActions]);
  const actionableHexes = useMemo(
    () => (state.phase === "network" && state.waitingOnHuman ? new Set(hexActions.keys()) : new Set<string>()),
    [hexActions, state.phase, state.waitingOnHuman],
  );

  async function send(request: () => Promise<GameState>, onDone: (next: GameState) => void) {
    setBusy(true);
    setError(null);
    setPreview(null);
    try {
      const next = await request();
      onDone(next);
      setState(next);
      setSelectedHex(null);
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
        const automatic = next.log.filter((entry) => entry.seq >= next.automaticLogStart);
        // A move nobody answered (the first of two network actions) keeps the previous summary.
        if (automatic.length === 0) return;
        setRecent(automatic);
        const hexes = changedHexes(state.tiles, next.tiles);
        if (isHexAction(action)) hexes.delete(hexKey(action.hex));
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
        setChanged(new Map());
      },
    );
  }

  function dismissRecent() {
    setRecent([]);
    setChanged(new Map());
  }

  useHotkeys({
    "mod+z": () => (state.canUndo && !busy ? undo() : false),
    u: () => (state.canUndo && !busy ? undo() : false),
    escape: () => {
      if (selectedHex === null && explicitFocus === null) return false;
      setSelectedHex(null);
      setExplicitFocus(null);
    },
  });

  function toggleFocus(corpId: string) {
    setExplicitFocus((current) => (current === corpId ? null : corpId));
  }

  function clickHex(hex: Axial) {
    setSelectedHex((current) => (current && hexKey(current) === hexKey(hex) ? null : hex));
    // Clicking a hex is about the acting corporation, so drop any other focus.
    setExplicitFocus(null);
  }

  const corpIds = state.corporations.map((c) => c.id);
  const displayRound = Math.min(state.roundNumber + 1, state.totalRounds);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand__mark">18BBY</span>
          <span className="brand__sub">Hyperspace commerce</span>
        </div>
        <div className="round">
          <span className="round__label">{state.roundLabel === "end" ? "End" : state.roundLabel}</span>
          <span className="round__meta">
            Round {displayRound} of {state.totalRounds} · {PHASE_NAMES[state.phase]}
          </span>
        </div>
        <div className="topbar__right">
          <button
            type="button"
            className="btn btn--small"
            disabled={!state.canUndo || busy}
            onClick={undo}
            title="Take back your last move, and anything played automatically after it"
          >
            <span>
              Undo <kbd>U</kbd>
            </span>
          </button>
          <span className="muted mono" title="Game id">
            {gameId}
          </span>
          <button type="button" className="btn btn--small" onClick={onLeave}>
            New game
          </button>
        </div>
      </header>

      <main className="game">
        <div className="game__main">
          <section className="panel panel--map">
            <HexMap
              board={board}
              tiles={state.tiles}
              corporations={state.corporations}
              focusCorp={focusCorp}
              actionableHexes={actionableHexes}
              selectedHex={selectedHex}
              preview={preview}
              changedHexes={changed}
              onHexClick={clickHex}
            />
            <MapLegend state={state} focusCorp={focusCorp} />
          </section>
          <StockMarket state={state} />
        </div>

        <aside className="game__side">
          <section className="panel panel--action">
            <h2 className="panel__title">
              <TurnHeading state={state} />
            </h2>
            {recent.length > 0 && (
              <div className="recent" role="status">
                <div className="recent__head">
                  <span>
                    Since your move
                    {changed.size > 0 && <span className="recent__note"> · changes outlined on the map</span>}
                  </span>
                  <button type="button" className="link" onClick={dismissRecent}>
                    hide
                  </button>
                </div>
                <ol>
                  {recent.slice(-6).map((entry, i) => (
                    <li key={i}>
                      <span
                        className="recent__actor"
                        style={corpIds.includes(entry.actor) ? { color: corporationColor(entry.actor, corpIds) } : undefined}
                      >
                        {actorLabel(state, entry.actor)}
                      </span>{" "}
                      {entry.text}
                    </li>
                  ))}
                  {recent.length > 6 && <li className="muted">…and {recent.length - 6} earlier (see log)</li>}
                </ol>
              </div>
            )}
            {error && (
              <div className="error" role="alert">
                <span>{error}</span>
                <button type="button" className="link" onClick={() => setError(null)}>
                  dismiss
                </button>
              </div>
            )}
            {state.phase === "game_over" ? (
              <GameOver state={state} onNewGame={onLeave} />
            ) : !state.waitingOnHuman ? (
              <p className="muted">Waiting for bots…</p>
            ) : state.phase === "stock" ? (
              <StockActions state={state} busy={busy} onAct={act} />
            ) : state.phase === "network" && actingCorp ? (
              <NetworkActions
                state={state}
                corp={actingCorp}
                selectedHex={selectedHex}
                busy={busy}
                onSelectHex={setSelectedHex}
                onPreview={setPreview}
                onAct={act}
              />
            ) : state.phase === "dividend" && actingCorp ? (
              <DividendActions state={state} corp={actingCorp} busy={busy} onAct={act} />
            ) : null}
          </section>
          <CorporationsPanel state={state} focusCorp={focusCorp} onToggle={toggleFocus} />
          <PlayersPanel state={state} />
          <LogPanel state={state} fresh={fresh} />
        </aside>
      </main>

    </div>
  );
}

function TurnHeading({ state }: { state: GameState }) {
  if (state.phase === "game_over") return <>Final standings</>;
  const who = playerName(state, state.currentPlayer);
  if (state.phase === "stock") return <>{who} to act</>;
  const corp = state.currentCorporation;
  const color = corp ? corporationColor(corp, state.corporations.map((c) => c.id)) : undefined;
  return (
    <>
      <span style={{ color }}>{corp}</span> operating
      <span className="panel__aside">president {who}</span>
    </>
  );
}

function MapLegend({ state, focusCorp }: { state: GameState; focusCorp: string | null }) {
  const corpIds = state.corporations.map((c) => c.id);
  const focus = findCorporation(state, focusCorp);
  return (
    <div className="legend">
      <span className="legend__item">
        <span className="legend__swatch legend__swatch--core" /> Core
      </span>
      <span className="legend__item">
        <span className="legend__swatch legend__swatch--mid" /> Mid Rim
      </span>
      <span className="legend__item">
        <span className="legend__swatch legend__swatch--outer" /> Outer Rim
      </span>
      <span className="legend__sep" />
      {state.corporations.map((c) => (
        <span key={c.id} className="legend__item">
          <span className="legend__line" style={{ background: corporationColor(c.id, corpIds) }} /> {c.id}
        </span>
      ))}
      {focus && focus.status === "floated" && (
        <span className="legend__focus">
          {focus.id}: {focus.reachablePlanets.length} planets reachable · revenue {focus.revenue.total}
        </span>
      )}
    </div>
  );
}
