import { describe, expect, it } from "vitest";
import type { GameState } from "../api";
import { effectsFor } from "./choreography";
import { corporation, deathStarState, gameState, logEntry, moveFrame, trackAt, withCorp } from "./fixtures";
import { applyFrame, describeMove, empireEvents, moveKind, playbackSteps, trackNote } from "./frames";
import { BASE_DURATION_MS, stepDuration } from "./timing";

/** OR1.1 under the Death Star rules: KDY (president Rax) is in its fleet step. */
function fleetStep(): GameState {
  return gameState({
    phase: "fleet",
    roundLabel: "OR1.1",
    currentPlayer: "P3",
    currentCorporation: "KDY",
    operatingOrder: ["KDY", "CEC"],
    deathStar: deathStarState(),
    corporations: [
      corporation("CEC", { status: "floated", treasury: 100, president: "P1", fleets: 1 }),
      corporation("KDY", { status: "floated", treasury: 300, president: "P3", fleets: 1 }),
    ],
  });
}

const sold = (state: GameState, count: number, price = 60): GameState => {
  const deathStar = state.deathStar!;
  return { ...state, deathStar: { ...deathStar, fleets: { ...deathStar.fleets, sold: count, price } } };
};

describe("fleet moves", () => {
  it("describes buying a fleet, and a price rise when a tier sells out", () => {
    const prev = sold(fleetStep(), 5);
    const after = sold(withCorp(prev, "KDY", { treasury: 240, fleets: 2 }), 6, 90);
    const frame = moveFrame({ type: "buy_fleet", cost: 60 }, after, { actor: "P3", corporation: "KDY", phase: "fleet" });
    expect(moveKind(frame, prev)).toEqual({
      kind: "buy_fleet",
      corp: "KDY",
      cost: 60,
      fleets: 2,
      price: { corp: "KDY", before: 60, after: 90 },
    });
    expect(describeMove(frame, prev)).toBe("KDY buys a fleet for 60, owning 2; fleets now cost 90");
  });

  it("describes finishing the fleet step", () => {
    const prev = fleetStep();
    const frame = moveFrame({ type: "finish_fleets" }, { ...prev, phase: "dividend" }, { actor: "P3", corporation: "KDY", phase: "fleet" });
    expect(describeMove(frame, prev)).toBe("KDY runs 1 fleet");
  });

  it("carries the track and supply into the display state", () => {
    const prev = fleetStep();
    const after = sold(withCorp(prev, "KDY", { fleets: 2 }), 1);
    const frame = moveFrame({ type: "buy_fleet", cost: 60 }, after, { actor: "P3", corporation: "KDY", phase: "fleet" });
    expect(applyFrame(prev, frame).deathStar?.fleets.sold).toBe(1);
  });

  it("flies a coin to the fleet supply and lights the corporation's fleets", () => {
    const kind = { kind: "buy_fleet" as const, corp: "KDY", cost: 60, fleets: 2, price: { corp: "KDY", before: 60, after: 60 } };
    const effects = effectsFor(kind, 1000, () => "#123456");
    expect(effects[0]).toMatchObject({ effect: "fly", to: "[data-fleet-supply]", label: "−60" });
    expect(effects[1]).toMatchObject({ effect: "highlight", target: ['[data-fleets-for="KDY"]', '[data-order-corp="KDY"]'] });
    expect(effects).toHaveLength(2);
  });

  it("has a duration for every new kind of step", () => {
    for (const kind of ["buy_fleet", "finish_fleets", "empire"] as const) {
      expect(BASE_DURATION_MS[kind]).toBeGreaterThan(0);
      expect(stepDuration(kind, 2)).toBe(BASE_DURATION_MS[kind] / 2);
    }
  });
});

/** The last dividend of OR1.2 fills the Frame stage; the seizure applies as the round ends. */
function seizureAtRoundEnd() {
  const prev = withCorp(
    { ...fleetStep(), phase: "dividend", roundLabel: "OR1.2", deathStar: trackAt(deathStarState(), 5, 0) },
    "KDY",
    { price: 70 },
  );
  const next: GameState = {
    ...withCorp(withCorp(prev, "KDY", { fleets: 0, price: 80 }), "CEC", { fleets: 0 }),
    phase: "stock",
    roundLabel: "SR2",
    currentCorporation: null,
    currentPlayer: "P1",
    deathStar: trackAt(deathStarState(), 6, 1),
  };
  const frame = moveFrame({ type: "dividend", choice: "pay" }, next, {
    actor: "P3",
    corporation: "KDY",
    phase: "dividend",
    revenue: 90,
    log: [logEntry(10, "KDY", "pays 90"), logEntry(11, "Empire", "seizes a fleet from KDY; it owns 0", "OR1.2")],
  });
  return { prev, next: { ...next, moves: [frame] }, frame };
}

describe("Empire events", () => {
  it("finds the seizure and which corporations lost a fleet", () => {
    const { prev, frame } = seizureAtRoundEnd();
    expect(empireEvents(prev, frame)).toEqual([{ type: "seizure", corps: ["CEC", "KDY"] }]);
  });

  it("adds a step for the seizure after the move, before the round banner", () => {
    const { prev, next } = seizureAtRoundEnd();
    const steps = playbackSteps(prev, next);
    expect(steps.map((s) => s.kind.kind)).toEqual(["dividend", "empire", "phase"]);
    expect(steps[0].caption).toMatch(/; \+1 Death Star cube \(6\/24\); Frame stage complete$/);
    expect(steps[1].caption).toBe("The Empire seizes a fleet from CEC, KDY");
    // The seizure shows where it happened, on the dividend view, with the fleets already gone.
    expect(steps[1].state).toMatchObject({ phase: "dividend", currentCorporation: "KDY" });
    expect(steps[1].state.corporations.map((c) => c.fleets)).toEqual([0, 0]);
  });

  it("shows the Empire's step even when the player's own move caused it", () => {
    const { prev, next, frame } = seizureAtRoundEnd();
    const own = { ...next, moves: [{ ...frame, automatic: false }] };
    expect(playbackSteps(prev, own).map((s) => s.kind.kind)).toEqual(["empire", "phase"]);
  });

  it("finds the site moving, and the launch", () => {
    const base = { ...fleetStep(), deathStar: trackAt(deathStarState(), 11, 1) };
    const moved = {
      ...trackAt(deathStarState(), 12, 2),
      sites: [
        { hex: [6, -2] as [number, number], region: "Outer Rim" as const, status: "vacated" as const },
        { hex: [-1, 5] as [number, number], region: "Mid Rim" as const, status: "active" as const },
      ],
    };
    const frame = moveFrame({ type: "pass" }, { ...base, deathStar: moved }, { actor: "P1", phase: "stock" });
    expect(empireEvents(base, frame)).toEqual([{ type: "site_move", from: [6, -2], to: [-1, 5] }]);
    expect(describeMove(frame, base)).toBe("Tim passes");

    const launched = {
      ...trackAt(deathStarState(), 24, 4),
      launched: true,
      sites: [moved.sites[0], { ...moved.sites[1], status: "launched" as const }],
    };
    const end = moveFrame({ type: "pass" }, { ...base, deathStar: launched }, { actor: "P1", phase: "stock" });
    const before = { ...base, deathStar: { ...moved, ...trackAt(moved, 23, 3), sites: moved.sites } };
    expect(empireEvents(before, end)).toEqual([{ type: "launch", at: [-1, 5] }]);
  });

  it("finds a bankruptcy in the move that ended the corporation's network actions", () => {
    const prev = { ...fleetStep(), phase: "network" as const };
    const after = withCorp({ ...prev, currentCorporation: "CEC" }, "KDY", { status: "closed", fleets: 0, treasury: 0 });
    const frame = moveFrame({ type: "no_action" }, after, { actor: "P3", corporation: "KDY", phase: "network" });
    expect(empireEvents(prev, frame)).toEqual([{ type: "bankrupt", corp: "KDY" }]);
    const steps = playbackSteps(prev, { ...after, moves: [frame] });
    expect(steps.map((s) => s.caption)).toEqual([
      "KDY takes no network action",
      "KDY (Admiral Rax) is bankrupt: no fleet, and no money for one. It closes and its shares are worthless",
    ]);
  });

  it("plays effects for each event", () => {
    const seizure = effectsFor({ kind: "empire", event: { type: "seizure", corps: ["KDY"] } }, 1000, () => "#000");
    expect(seizure.map((e) => e.effect)).toEqual(["highlight", "pop"]);
    const move = effectsFor({ kind: "empire", event: { type: "site_move", from: [6, -2], to: [-1, 5] } }, 1000, () => "#000");
    expect(move.slice(1).map((e) => (e.effect === "highlight" ? e.target : null))).toEqual(['[data-hex="6,-2"]', '[data-hex="-1,5"]']);
    const bankrupt = effectsFor({ kind: "empire", event: { type: "bankrupt", corp: "KDY" } }, 1000, () => "#000");
    expect(bankrupt[0]).toMatchObject({ effect: "pop", label: "Bankrupt" });
  });

  it("has nothing to say without the Death Star rules", () => {
    const prev = gameState();
    const frame = moveFrame({ type: "pass" }, prev, { actor: "P1" });
    expect(empireEvents(prev, frame)).toEqual([]);
    expect(trackNote(undefined, undefined)).toBe("");
  });
});
