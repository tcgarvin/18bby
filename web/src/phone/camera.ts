/**
 * What the phone's map frames, on your turn and during a replay. A phone can't show the board at a
 * tappable size, but a turn only needs the corner the acting corporation works in.
 */

import type { Axial, Board, CorporationState, GameState } from "../api";
import { fitViewBox } from "../components/HexMap";
import { sitePlanet } from "../deathstar";
import { DIRECTIONS, neighbor } from "../hex";
import type { PlaybackStep } from "../playback/frames";
import { CAMERA_GLIDE_MS } from "../playback/timing";
import { findCorporation } from "../selectors";

/** How near the picked hex another hex must be to stay in frame while the options are open. */
const SELECTION_RADIUS = 3;

function hexDistance(a: Axial, b: Axial): number {
  const dq = a[0] - b[0];
  const dr = a[1] - b[1];
  return (Math.abs(dq) + Math.abs(dr) + Math.abs(dq + dr)) / 2;
}

/** Hexes the corporation's network touches: served tiles, reachable planets and its homeworld. */
export function networkHexes(state: GameState, board: Board, corp: CorporationState): Axial[] {
  const names = new Set([...corp.reachablePlanets, corp.homeworld]);
  const site = sitePlanet(state.deathStar);
  const hubs = site ? [...board.planets, site] : board.planets;
  return [
    ...state.tiles.filter((t) => t.service.includes(corp.id)).map((t) => t.hex),
    ...hubs.filter((p) => names.has(p.name)).map((p) => p.hex),
  ];
}

/** The frame for a decision: the acting corporation's network and every hex it can act on. */
export function turnHexes(state: GameState, board: Board, targets: Axial[]): Axial[] {
  const corp = findCorporation(state, state.currentCorporation);
  return [...(corp ? networkHexes(state, board, corp) : []), ...targets];
}

/**
 * The frame while a hex's options are open, when the map has less room: the hex with its
 * neighbours, so the previewed lane's ends show, and whatever of the turn's frame is close by.
 */
export function selectionHexes(selected: Axial, turn: Axial[]): Axial[] {
  const around = DIRECTIONS.map((direction) => neighbor(selected, direction));
  return [selected, ...around, ...turn.filter((hex) => hexDistance(hex, selected) <= SELECTION_RADIUS)];
}

/**
 * The frame a replay step needs, or null to leave the camera where it is. Moves that change the
 * board frame their corporation's network; the Empire's frame what it touched. Everything else
 * lands on the strips, so the map holds still and the viewer keeps their place.
 */
export function stepHexes(step: PlaybackStep, board: Board): Axial[] | null {
  const { kind } = step;
  switch (kind.kind) {
    case "chart":
    case "upgrade":
    case "service":
    case "build_facility":
    case "surrender_facility": {
      const corp = findCorporation(step.state, kind.corp);
      return [...(corp ? networkHexes(step.state, board, corp) : []), kind.hex];
    }
    case "empire": {
      const { event } = kind;
      if (event.type === "site_move") return [event.from, event.to];
      if (event.type === "launch") return [event.at];
      if (event.type === "seizure" && (event.taken?.length ?? 0) > 0) return (event.taken ?? []).map((facility) => facility.hex);
      return null;
    }
    default:
      return null;
  }
}

/** Each step's wait for the camera at 1×: a glide where its frame differs from the last one. */
export function replayLeads(steps: PlaybackStep[], board: Board): number[] {
  let shown: string | null = null;
  return steps.map((step) => {
    const hexes = stepHexes(step, board);
    if (hexes === null) return 0;
    const box = fitViewBox(hexes);
    if (box === shown) return 0;
    shown = box;
    return CAMERA_GLIDE_MS;
  });
}
