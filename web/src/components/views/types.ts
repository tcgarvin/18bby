import type { Action, Board, GameState } from "../../api";
import type { PlaybackStep } from "../../playback/frames";

/** Things not featured in a view, opened over it from the top bar (M, K, L). */
export type OverlayKind = "map" | "market" | "log";

/**
 * What every phase view receives. Views are presentational: they draw `state`, which may be an
 * intermediate state from the replay engine rather than the latest one from the server, and
 * they offer controls only when `interactive` is true.
 */
export interface ViewProps {
  /** The state to draw (the container's display state). */
  state: GameState;
  board: Board;
  /** True when a human may act on this state: it is the latest one and a human is to move. */
  interactive: boolean;
  /** A request is in flight; controls stay visible but disabled. */
  busy: boolean;
  /** Whether the view's keyboard shortcuts are live (off while an overlay is open). */
  keyboard: boolean;
  /** Hexes changed by bots or forced moves since your move, for outlining on the map. */
  changedHexes: Map<string, string[]>;
  /** The opponent move being replayed, or null when the view shows the live game. */
  replayStep: PlaybackStep | null;
  /** Submit one of `state.legalActions`, unchanged. */
  onAct: (action: Action) => void;
  onOpen: (overlay: OverlayKind) => void;
}
