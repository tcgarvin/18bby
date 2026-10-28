/**
 * The two halves of the game screen and which one the player is looking at. "Shares" is the
 * stock round's layout (players, corporation cards, stock market); "Map" is the operating layout
 * (the map with the corporations down the side). The current phase's view is live: the only one
 * that offers actions. The other draws the same state read-only, for browsing. At game over the
 * results are the default and both halves are read-only.
 */

import type { GameState } from "./api";

export type GameView = "shares" | "map" | "results";

type Phase = GameState["phase"];

/** The view that belongs to `phase`: where its actions are offered. */
export function liveView(phase: Phase): GameView {
  if (phase === "stock") return "shares";
  if (phase === "game_over") return "results";
  return "map";
}

/** The views the toggle offers in `phase`, in the order it shows them. */
export function availableViews(phase: Phase): GameView[] {
  return phase === "game_over" ? ["shares", "map", "results"] : ["shares", "map"];
}

/**
 * The player's choice of view, remembered with the phase and replay it was made in. `view` is
 * null while the screen follows the live view.
 */
export interface ViewSelection {
  view: GameView | null;
  phase: Phase;
  playing: boolean;
}

export function initialSelection(phase: Phase, playing: boolean): ViewSelection {
  return { view: null, phase, playing };
}

/**
 * The selection carried to a new render: a phase change or the start of a replay snaps back to
 * the live view, so a turn (or an opponent's move) is never shown on a view that cannot act on
 * it. Returns `selection` itself when nothing changed, so it can be compared by identity.
 */
export function followSelection(selection: ViewSelection, phase: Phase, playing: boolean): ViewSelection {
  if (selection.phase !== phase || (playing && !selection.playing)) return initialSelection(phase, playing);
  if (selection.playing !== playing) return { ...selection, playing };
  return selection;
}

/** The view on screen: the chosen one, or the live one when the player has not chosen. */
export function shownView(selection: ViewSelection): GameView {
  const views = availableViews(selection.phase);
  return selection.view !== null && views.includes(selection.view) ? selection.view : liveView(selection.phase);
}

/**
 * The view a view hotkey asks for: V steps to the next view (a flip between Shares and Map),
 * M picks the map, S (or K, from the old market overlay) the shares. Null for any other key, or a
 * view this phase does not offer.
 */
export function viewForKey(key: string, shown: GameView, phase: Phase): GameView | null {
  const views = availableViews(phase);
  const wanted: GameView | null =
    key === "v"
      ? views[(views.indexOf(shown) + 1) % views.length]
      : key === "m"
        ? "map"
        : key === "s" || key === "k"
          ? "shares"
          : null;
  return wanted !== null && views.includes(wanted) ? wanted : null;
}

const VIEW_NAMES: Record<GameView, string> = { shares: "Shares", map: "Map", results: "Results" };

export function viewName(view: GameView): string {
  return VIEW_NAMES[view];
}

/**
 * The banner over a browsed view: what it is, why nothing can be done in it, and the label of the
 * button back to the live view. The round and step are already in the top bar, so the text stays
 * short. Null when `shown` is the live view.
 */
export function browseBanner(phase: Phase, shown: GameView): { text: string; back: string } | null {
  const live = liveView(phase);
  if (shown === live) return null;
  const note = phase === "game_over" ? "final position" : "read-only";
  return {
    text: `${viewName(shown)} · ${note}`,
    back: live === "results" ? "View results" : `Back to ${viewName(live)}`,
  };
}
