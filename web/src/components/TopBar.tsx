import type { GameState } from "../api";
import type { GameView } from "../gameView";
import { viewName } from "../gameView";
import { useRules } from "../help/rulesContext";
import { corpColor, phaseSteps, playerName } from "../selectors";
import { Help } from "./Help";

interface TopBarProps {
  state: GameState;
  gameId: string;
  /** The views the toggle offers, in order. */
  views: GameView[];
  /** The view on screen. */
  shownView: GameView;
  /** The current phase's view, marked Live; null when none is (game over). The marker is always
   * rendered (hidden when not live) so the segments keep their width. */
  liveView: GameView | null;
  onView: (view: GameView) => void;
  logOpen: boolean;
  onToggleLog: () => void;
  canUndo: boolean;
  onUndo: () => void;
  onLeave: () => void;
}

const VIEW_TITLES: Record<GameView, string> = {
  shares: "Players, corporations and the stock market (S; V flips)",
  map: "The map, with the corporations down the side (M; V flips)",
  results: "Final standings",
};

/** Brand, where the game is (SR › OR › OR), who is acting, the view toggle, Log, Undo and New game. */
export function TopBar({
  state,
  gameId,
  views,
  shownView,
  liveView,
  onView,
  logOpen,
  onToggleLog,
  canUndo,
  onUndo,
  onLeave,
}: TopBarProps) {
  const rules = useRules();
  const steps = phaseSteps(state.roundLabel, rules.operatingRoundsPerStockRound, state.totalRounds);
  const displayRound = Math.min(state.roundNumber + 1, state.totalRounds);
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand__mark">18BBY</span>
      </div>

      <nav className="stepper" aria-label="Round">
        <span className="stepper__round">
          Round {displayRound}/{state.totalRounds}
          <Help topic="round" />
        </span>
        <ol className="stepper__steps">
          {steps.map((step) => (
            <li key={step.label} className={`stepper__step stepper__step--${step.stage}`} aria-current={step.stage === "current" ? "step" : undefined}>
              <span className="stepper__pill">{step.label}</span>
            </li>
          ))}
        </ol>
      </nav>

      <div className="acting" aria-live="polite">
        <Acting state={state} />
      </div>

      <div className="topbar__right">
        <div className="view-switch" role="group" aria-label="Game view">
          {views.map((view) => (
            <button
              type="button"
              key={view}
              className="view-switch__button"
              aria-pressed={shownView === view}
              onClick={() => onView(view)}
              title={VIEW_TITLES[view]}
            >
              {viewName(view)}
              {view !== "results" && (
                <span className="view-switch__live" data-live={view === liveView} aria-hidden={view !== liveView}>
                  Live
                </span>
              )}
            </button>
          ))}
        </div>
        <button type="button" className="btn btn--small" aria-pressed={logOpen} onClick={onToggleLog} title="Show the game log">
          <span>
            Log <kbd>L</kbd>
          </span>
        </button>
        <button
          type="button"
          className="btn btn--small"
          disabled={!canUndo}
          onClick={onUndo}
          title="Take back your last move, and anything played automatically after it"
        >
          <span>
            Undo <kbd>U</kbd>
          </span>
        </button>
        <span className="topbar__id mono" title="Game id">
          {gameId}
        </span>
        <button type="button" className="btn btn--small" onClick={onLeave}>
          New game
        </button>
      </div>
    </header>
  );
}

function Acting({ state }: { state: GameState }) {
  if (state.phase === "game_over") return <span className="acting__phase">Game over</span>;
  const who = playerName(state, state.currentPlayer);
  const bot = state.players.find((p) => p.id === state.currentPlayer)?.isBot ?? false;
  if (state.phase === "stock") {
    return (
      <>
        <span className="acting__phase">
          Stock round
          <Help topic="stockRound" />
        </span>
        <span className="acting__who">
          {who}
          {bot ? " (bot)" : ""} to act
        </span>
      </>
    );
  }
  const corp = state.currentCorporation;
  const facilities = state.facilities !== undefined;
  return (
    <>
      <span className="acting__phase">
        {state.phase === "network"
          ? "Build"
          : state.phase === "fleet"
            ? facilities
              ? "Build facilities"
              : "Buy fleets"
            : "Pay or withhold"}
        <Help
          topic={
            state.phase === "network" ? "networkAction" : state.phase === "fleet" ? (facilities ? "facility" : "fleet") : "dividend"
          }
        />
      </span>
      {corp && (
        <span className="acting__who">
          <span className="chip" style={{ background: corpColor(state, corp) }}>
            {corp}
          </span>{" "}
          {who}
          {bot ? " (bot)" : ""}
        </span>
      )}
    </>
  );
}
