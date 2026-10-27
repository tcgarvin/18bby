import type { GameState } from "../api";
import { useRules } from "../help/rulesContext";
import { corpColor, phaseSteps, playerName } from "../selectors";
import { Help } from "./Help";
import type { OverlayKind } from "./views/types";

interface TopBarProps {
  state: GameState;
  gameId: string;
  /** Overlays this view offers (the featured content has no toggle). */
  overlays: OverlayKind[];
  openOverlay: OverlayKind | null;
  onToggleOverlay: (overlay: OverlayKind) => void;
  canUndo: boolean;
  onUndo: () => void;
  onLeave: () => void;
}

const OVERLAY_BUTTONS: Record<OverlayKind, { label: string; key: string; title: string }> = {
  map: { label: "Map", key: "M", title: "Show the map" },
  market: { label: "Market", key: "K", title: "Show the stock market" },
  log: { label: "Log", key: "L", title: "Show the game log" },
};

/** Brand, where the game is (SR › OR › OR), who is acting, overlay toggles, Undo and New game. */
export function TopBar({ state, gameId, overlays, openOverlay, onToggleOverlay, canUndo, onUndo, onLeave }: TopBarProps) {
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
        <div className="toggles" role="group" aria-label="Show">
          {(["map", "market", "log"] as OverlayKind[]).map((kind) => {
            const button = OVERLAY_BUTTONS[kind];
            const available = overlays.includes(kind);
            return (
              <button
                type="button"
                key={kind}
                className={`toggle-btn${openOverlay === kind ? " toggle-btn--on" : ""}`}
                disabled={!available}
                aria-pressed={openOverlay === kind}
                onClick={() => onToggleOverlay(kind)}
                title={available ? button.title : `${button.label} is already on screen`}
              >
                {button.label}
                <kbd>{button.key}</kbd>
              </button>
            );
          })}
        </div>
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
