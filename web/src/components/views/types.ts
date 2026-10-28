import type { Action, Board, GameState } from "../../api";
import type { GameView } from "../../gameView";
import type { PlaybackStep } from "../../playback/frames";

/**
 * What every view receives. Views are presentational: they draw `state`, which may be an
 * intermediate state from the replay engine rather than the latest one from the server, and
 * they offer controls only when `interactive` is true.
 */
export interface ViewProps {
  /** The state to draw (the container's display state). */
  state: GameState;
  board: Board;
  /**
   * True when a human may act on this state: this is the live view, the state is the latest
   * one and a human is to move. Never true while `browsing`.
   */
  interactive: boolean;
  /**
   * The player is looking at the view that does not belong to the current phase (Shares during
   * an operating round, the Map during a stock round, either at game over). It draws the same
   * state read-only, with no action controls, and words its prompts for an onlooker.
   */
  browsing: boolean;
  /** A request is in flight; controls stay visible but disabled. */
  busy: boolean;
  /** Whether the view's keyboard shortcuts are live (off while the log is open or a replay runs). */
  keyboard: boolean;
  /** Hexes changed by bots or forced moves since your move, for outlining on the map. */
  changedHexes: Map<string, string[]>;
  /** The opponent move being replayed, or null when the view shows the live game. */
  replayStep: PlaybackStep | null;
  /** Submit one of `state.legalActions`, unchanged. */
  onAct: (action: Action) => void;
  /** Switch the screen to another view (the stock round's map thumbnail opens the Map). */
  onView: (view: GameView) => void;
}
