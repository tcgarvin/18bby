import { describe, expect, it } from "vitest";
import type { Axial, Board, GameState } from "../api";
import { corporation, gameState } from "../playback/fixtures";
import type { MoveKind, PlaybackStep } from "../playback/frames";
import { CAMERA_GLIDE_MS } from "../playback/timing";
import { networkHexes, replayLeads, selectionHexes, stepHexes, turnHexes } from "./camera";
import { interpolateBox } from "./useViewBoxGlide";

const planet = (name: string, hex: Axial) => ({ name, hex, tags: ["R"], region: "Outer Rim" }) as Board["planets"][number];
const board = {
  hexes: [],
  planets: [planet("Home", [0, 0]), planet("Far", [5, 0]), planet("Other", [-5, 0])],
} as unknown as Board;

const state: GameState = gameState({
  phase: "network",
  currentCorporation: "CEC",
  tiles: [
    { hex: [1, 0], exits: ["E", "W"], service: ["CEC"] },
    { hex: [-1, 0], exits: ["E", "W"], service: ["KDY"] },
  ],
  corporations: [
    corporation("CEC", { status: "floated", homeworld: "Home", reachablePlanets: ["Far"] }),
    corporation("KDY", { status: "floated", homeworld: "Other", reachablePlanets: [] }),
  ],
});

function step(kind: MoveKind): PlaybackStep {
  return { frame: null, kind, caption: "", before: state, state };
}

const chart = (corp: string, hex: Axial) => step({ kind: "chart", corp, hex, exits: ["E", "W"], cost: 60 });
const quiet = (corp: string) => step({ kind: "no_action", corp });

describe("networkHexes", () => {
  it("is the corporation's served tiles, reachable planets and homeworld", () => {
    const hexes = networkHexes(state, board, state.corporations[0]);
    expect(hexes).toEqual(expect.arrayContaining([[1, 0], [0, 0], [5, 0]]));
    expect(hexes).not.toContainEqual([-1, 0]);
    expect(hexes).not.toContainEqual([-5, 0]);
  });
});

describe("turnHexes", () => {
  it("frames the acting corporation's network and its targets", () => {
    const hexes = turnHexes(state, board, [[2, 2]]);
    expect(hexes).toEqual(expect.arrayContaining([[1, 0], [2, 2]]));
  });
});

describe("selectionHexes", () => {
  it("keeps the picked hex's neighbours and drops what is far away", () => {
    const hexes = selectionHexes([0, 0], [[1, 1], [6, 0]]);
    expect(hexes).toContainEqual([0, 0]);
    expect(hexes).toContainEqual([1, 0]);
    expect(hexes).toContainEqual([1, 1]);
    expect(hexes).not.toContainEqual([6, 0]);
  });
});

describe("stepHexes", () => {
  it("frames a builder's network and the hex it built on", () => {
    expect(stepHexes(chart("CEC", [3, 3]), board)).toEqual(expect.arrayContaining([[3, 3], [1, 0], [5, 0]]));
  });

  it("leaves the camera alone for moves that land on the strips", () => {
    expect(stepHexes(quiet("CEC"), board)).toBeNull();
    expect(stepHexes(step({ kind: "pass", player: "P1", priceChanges: [] }), board)).toBeNull();
  });

  it("frames what the Empire touched", () => {
    const move = step({ kind: "empire", event: { type: "site_move", from: [1, 1], to: [2, 2] } });
    expect(stepHexes(move, board)).toEqual([[1, 1], [2, 2]]);
  });

  it("leaves the camera alone for a seizure that has taken nothing yet", () => {
    expect(stepHexes(step({ kind: "empire", event: { type: "seizure", corps: [], demanded: ["CEC"] } }), board)).toBeNull();
  });
});

describe("replayLeads", () => {
  it("waits for the camera only where the frame changes", () => {
    const steps = [quiet("CEC"), chart("CEC", [1, 0]), quiet("CEC"), chart("CEC", [1, 0]), chart("KDY", [-1, 0])];
    expect(replayLeads(steps, board)).toEqual([0, CAMERA_GLIDE_MS, 0, 0, CAMERA_GLIDE_MS]);
  });
});

describe("interpolateBox", () => {
  it("runs from one view to the other", () => {
    expect(interpolateBox("0 0 10 10", "100 100 20 20", 0)).toBe("0.0 0.0 10.0 10.0");
    expect(interpolateBox("0 0 10 10", "100 100 20 20", 1)).toBe("100.0 100.0 20.0 20.0");
    expect(interpolateBox("0 0 10 10", "100 100 20 20", 0.5)).toBe("50.0 50.0 15.0 15.0");
  });
});
