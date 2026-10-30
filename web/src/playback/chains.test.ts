import { describe, expect, it } from "vitest";
import type { GameState, PlanetFacilities } from "../api";
import { effectsFor } from "./choreography";
import { corporation, deathStarState, gameState, logEntry, moveFrame, planetFacilities, trackAt, withCorp, withFacilities } from "./fixtures";
import { empireEvents, moveKind, playbackSteps } from "./frames";
import { BASE_DURATION_MS } from "./timing";

const KUAT: [number, number] = [-3, 2];
const SULLUST: [number, number] = [1, 3];

/** The last dividend of OR1.2 under the chain rules, before the Frame stage fills. */
function lastDividend(): GameState {
  return withFacilities(
    gameState({
      phase: "dividend",
      roundLabel: "OR1.2",
      currentPlayer: "P3",
      currentCorporation: "KDY",
      operatingOrder: ["KDY", "CEC"],
      deathStar: trackAt(deathStarState(), 5, 0),
      corporations: [
        corporation("CEC", { status: "floated", president: "P1", fleets: 1 }),
        corporation("KDY", { status: "floated", president: "P3", fleets: 2 }),
      ],
    }),
    [
      planetFacilities("Kuat", KUAT, { facilities: [{ owner: "KDY", build: 1 }] }),
      planetFacilities("Sullust", SULLUST, { facilities: [{ owner: "KDY", build: 2 }] }),
    ],
  );
}

/** The dividend fills the stage, and the Empire demands a facility from KDY and CEC. */
function demand() {
  const prev = lastDividend();
  const next: GameState = {
    ...prev,
    phase: "surrender",
    deathStar: { ...trackAt(deathStarState(), 6, 1), fleets: { ...deathStarState().fleets, item: "facility" } },
    facilities: { ...prev.facilities!, surrenderQueue: ["KDY", "CEC"] },
  };
  const frame = moveFrame({ type: "dividend", choice: "pay" }, next, {
    actor: "P3",
    corporation: "KDY",
    phase: "dividend",
    revenue: 90,
    log: [logEntry(10, "KDY", "pays 90"), logEntry(11, "Empire", "demands a facility from KDY, CEC", "OR1.2")],
  });
  return { prev, next, frame };
}

describe("seizures under the chain rules", () => {
  it("shows the demand, taking nothing yet", () => {
    const { prev, frame } = demand();
    expect(empireEvents(prev, frame)).toEqual([{ type: "seizure", corps: [], taken: [], demanded: ["KDY", "CEC"] }]);
    const steps = playbackSteps(prev, { ...demand().next, moves: [frame] });
    expect(steps.map((s) => s.kind.kind)).toEqual(["dividend", "empire"]);
    expect(steps[1].caption).toBe("The Empire demands a facility from KDY and CEC; each chooses which to give up");
    const effects = effectsFor(steps[1].kind, 1000, () => "#000");
    expect(effects.filter((e) => e.effect === "pop").map((e) => (e.effect === "pop" ? e.label : ""))).toEqual([
      "Surrender 1",
      "Surrender 1",
    ]);
  });

  it("describes each surrender and lights the planet that turned Imperial", () => {
    const { next: prev } = demand();
    const sullust: PlanetFacilities = planetFacilities("Sullust", SULLUST, { facilities: [{ owner: "Empire", build: 2 }] });
    const after: GameState = {
      ...withCorp(prev, "KDY", { fleets: 1 }),
      currentCorporation: "CEC",
      currentPlayer: "P1",
      facilities: {
        ...prev.facilities!,
        planets: prev.facilities!.planets.map((p) => (p.name === "Sullust" ? sullust : p)),
        surrenderQueue: ["CEC"],
      },
    };
    const action = { type: "surrender_facility" as const, planet: SULLUST };
    const frame = moveFrame(action, after, {
      actor: "P3",
      corporation: "KDY",
      phase: "surrender",
      planets: [sullust],
      log: [logEntry(12, "Empire", "takes over KDY's facility at Sullust; it owns 1", "OR1.2")],
    });
    expect(moveKind(frame, prev)).toEqual({ kind: "surrender_facility", corp: "KDY", planet: "Sullust", hex: SULLUST, facilities: 1 });
    const [step] = playbackSteps(prev, { ...after, moves: [frame] });
    expect(step.caption).toBe("KDY gives the Empire its facility at Sullust, keeping 1 facility");
    expect(step.state.phase).toBe("surrender");
    expect(step.state.currentCorporation).toBe("KDY");
    const effects = effectsFor(step.kind, 1000, () => "#000");
    expect(effects.map((e) => (e.effect === "highlight" ? e.target : e.effect === "pop" ? e.label : ""))).toEqual([
      '[data-hex="1,3"]',
      "−1 facility",
    ]);
    expect(BASE_DURATION_MS.surrender_facility).toBeGreaterThan(0);
  });
});
