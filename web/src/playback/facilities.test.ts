import { describe, expect, it } from "vitest";
import type { GameState, PlanetFacilities } from "../api";
import { effectsFor } from "./choreography";
import { corporation, deathStarState, gameState, logEntry, moveFrame, planetFacilities, trackAt, withCorp, withFacilities } from "./fixtures";
import { applyFrame, describeMove, empireEvents, moveKind, playbackSteps } from "./frames";
import { BASE_DURATION_MS } from "./timing";

const CORELLIA: [number, number] = [-5, 3];
const KUAT: [number, number] = [-3, 2];

/** OR1.1 under the facility rules: KDY (president Rax) is in its facility step. */
function facilityStep(): GameState {
  return withFacilities(
    gameState({
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
    }),
    [
      planetFacilities("Corellia", CORELLIA, { exits: 2, unclaimed: 2, facilities: [{ owner: "CEC", build: 0 }], freeSlots: 1 }),
      planetFacilities("Kuat", KUAT, { exits: 2, unclaimed: 1, claimed: ["NE"], dangling: ["W"], facilities: [{ owner: "KDY", build: 1 }], freeSlots: 1 }),
    ],
  );
}

/** Kuat with a second KDY facility, its new exit given to the W lane. */
const kuatBuilt: PlanetFacilities = planetFacilities("Kuat", KUAT, {
  exits: 3,
  unclaimed: 1,
  claimed: ["NE", "W"],
  facilities: [
    { owner: "KDY", build: 1 },
    { owner: "KDY", build: 2 },
  ],
  freeSlots: 0,
});

function withPlanet(state: GameState, planet: PlanetFacilities): GameState {
  const facilities = state.facilities!;
  return { ...state, facilities: { ...facilities, planets: facilities.planets.map((p) => (p.name === planet.name ? planet : p)) } };
}

describe("facility builds", () => {
  it("describes a build, the lane its exit went to, and a price rise", () => {
    const prev = facilityStep();
    const after = withPlanet(withCorp(prev, "KDY", { treasury: 240, fleets: 2 }), kuatBuilt);
    const risen = { ...after, deathStar: { ...after.deathStar!, fleets: { ...after.deathStar!.fleets, price: 90 } } };
    const action = { type: "build_facility" as const, planet: KUAT, exit: "W" as const, cost: 60 };
    const frame = moveFrame(action, risen, { actor: "P3", corporation: "KDY", phase: "fleet", planets: [kuatBuilt] });
    expect(moveKind(frame, prev)).toEqual({
      kind: "build_facility",
      corp: "KDY",
      planet: "Kuat",
      hex: KUAT,
      exit: "W",
      cost: 60,
      facilities: 2,
      price: { corp: "KDY", before: 60, after: 90 },
    });
    expect(describeMove(frame, prev)).toBe(
      "KDY builds a facility at Kuat for 60, giving its new exit to the W lane, owning 2; facilities now cost 90",
    );
  });

  it("describes a build that leaves its exit open", () => {
    const prev = facilityStep();
    const after = withCorp(prev, "KDY", { treasury: 240, fleets: 2 });
    const frame = moveFrame({ type: "build_facility", planet: CORELLIA, cost: 60 }, after, { actor: "P3", corporation: "KDY", phase: "fleet" });
    expect(describeMove(frame, prev)).toBe("KDY builds a facility at Corellia for 60, leaving its new exit open, owning 2");
  });

  it("describes finishing the facility step", () => {
    const prev = facilityStep();
    const frame = moveFrame({ type: "finish_fleets" }, { ...prev, phase: "dividend" }, { actor: "P3", corporation: "KDY", phase: "fleet" });
    expect(describeMove(frame, prev)).toBe("KDY runs 1 facility");
    expect(effectsFor(moveKind(frame, prev), 1000, () => "#000")[0]).toMatchObject({ effect: "pop", label: "1 facility" });
  });

  it("merges only the planets a frame changed into the display state", () => {
    const prev = { ...facilityStep(), facilities: { ...facilityStep().facilities!, options: [{ action: { type: "build_facility" as const, planet: KUAT, cost: 60 }, revenue: 0, reaches: [], lane: [] }] } };
    const after = withPlanet(withCorp(prev, "KDY", { fleets: 2 }), kuatBuilt);
    const frame = moveFrame({ type: "build_facility", planet: KUAT, exit: "W", cost: 60 }, after, {
      actor: "P3",
      corporation: "KDY",
      phase: "fleet",
      planets: [kuatBuilt],
    });
    const applied = applyFrame(prev, frame);
    expect(applied.facilities?.planets.map((p) => p.name)).toEqual(["Corellia", "Kuat"]);
    expect(applied.facilities?.planets[1]).toBe(kuatBuilt);
    expect(applied.facilities?.planets[0]).toBe(prev.facilities.planets[0]);
    expect(applied.facilities?.options).toEqual([]);
  });

  it("flies a coin to the planet and lights the builder's facilities", () => {
    const kind = {
      kind: "build_facility" as const,
      corp: "KDY",
      planet: "Kuat",
      hex: KUAT,
      cost: 60,
      facilities: 2,
      price: { corp: "KDY", before: 60, after: 60 },
    };
    const effects = effectsFor(kind, 1000, () => "#123456");
    expect(effects[0]).toMatchObject({ effect: "fly", to: '[data-hex="-3,2"]', label: "−60", variant: "coin" });
    expect(effects.slice(1).map((e) => (e.effect === "highlight" ? e.target : null))).toEqual([
      '[data-hex="-3,2"]',
      ['[data-fleets-for="KDY"]', '[data-order-corp="KDY"]'],
    ]);
    expect(BASE_DURATION_MS.build_facility).toBeGreaterThan(0);
  });
});

/** The last dividend of OR1.2 fills the Frame stage; the Empire takes over the nearest facilities. */
function seizureAtRoundEnd() {
  const prev = { ...facilityStep(), phase: "dividend" as const, roundLabel: "OR1.2", deathStar: trackAt(deathStarState(), 5, 0) };
  const corellia = planetFacilities("Corellia", CORELLIA, { exits: 2, unclaimed: 2, facilities: [{ owner: "Empire", build: 0 }], freeSlots: 1 });
  const kuat = planetFacilities("Kuat", KUAT, { exits: 2, unclaimed: 1, claimed: ["NE"], dangling: ["W"], facilities: [{ owner: "Empire", build: 1 }], freeSlots: 1 });
  const next: GameState = {
    ...withPlanet(withPlanet(withCorp(withCorp(prev, "KDY", { fleets: 0 }), "CEC", { fleets: 0 }), corellia), kuat),
    phase: "stock",
    roundLabel: "SR2",
    currentCorporation: null,
    currentPlayer: "P1",
    deathStar: { ...trackAt(deathStarState(), 6, 1), fleets: { ...deathStarState().fleets, item: "facility" } },
  };
  const frame = moveFrame({ type: "dividend", choice: "pay" }, next, {
    actor: "P3",
    corporation: "KDY",
    phase: "dividend",
    revenue: 90,
    planets: [corellia, kuat],
    log: [logEntry(10, "KDY", "pays 90"), logEntry(11, "Empire", "takes over CEC's facility at Corellia; it owns 0", "OR1.2")],
  });
  return { prev, next: { ...next, moves: [frame] }, frame };
}

describe("seizures under the facility rules", () => {
  it("names each facility that turned Imperial", () => {
    const { prev, frame } = seizureAtRoundEnd();
    expect(empireEvents(prev, frame)).toEqual([
      {
        type: "seizure",
        corps: ["CEC", "KDY"],
        taken: [
          { corp: "CEC", planet: "Corellia", hex: CORELLIA },
          { corp: "KDY", planet: "Kuat", hex: KUAT },
        ],
      },
    ]);
  });

  it("captions the seizure and shows it with the facilities already Imperial", () => {
    const { prev, next } = seizureAtRoundEnd();
    const steps = playbackSteps(prev, next);
    expect(steps.map((s) => s.kind.kind)).toEqual(["dividend", "empire", "phase"]);
    expect(steps[1].caption).toBe("The Empire takes over CEC's facility at Corellia and KDY's at Kuat; they are Imperial now");
    expect(steps[1].state.facilities?.planets.flatMap((p) => p.facilities.map((f) => f.owner))).toEqual(["Empire", "Empire"]);
  });

  it("pops the loss on each corporation and lights the seized planets", () => {
    const { prev, frame } = seizureAtRoundEnd();
    const [event] = empireEvents(prev, frame);
    const effects = effectsFor({ kind: "empire", event }, 1000, () => "#000");
    expect(effects.filter((e) => e.effect === "pop").map((e) => (e.effect === "pop" ? e.label : ""))).toEqual(["−1 facility", "−1 facility"]);
    expect(effects.filter((e) => e.effect === "highlight").map((e) => (e.effect === "highlight" ? e.target : null))).toEqual([
      "[data-death-star-track]",
      '[data-hex="-5,3"]',
      '[data-hex="-3,2"]',
    ]);
  });

  it("says when there was nothing to take", () => {
    const prev = { ...facilityStep(), deathStar: trackAt(deathStarState(), 5, 0) };
    const after = { ...prev, deathStar: trackAt(deathStarState(), 6, 1) };
    const frame = moveFrame({ type: "pass" }, after, { actor: "P1", phase: "stock" });
    const [event] = empireEvents(prev, frame);
    expect(event).toEqual({ type: "seizure", corps: [], taken: [] });
    expect(playbackSteps(prev, { ...after, moves: [frame] })[1].caption).toBe("The Empire finds no facilities to take over");
  });

  it("explains a bankruptcy in facility terms", () => {
    const prev = { ...facilityStep(), phase: "network" as const };
    const after = withCorp({ ...prev, currentCorporation: "CEC" }, "KDY", { status: "closed", fleets: 0, treasury: 0 });
    const frame = moveFrame({ type: "no_action" }, after, { actor: "P3", corporation: "KDY", phase: "network" });
    expect(playbackSteps(prev, { ...after, moves: [frame] })[1].caption).toBe(
      "KDY (Admiral Rax) is bankrupt: no facility, and none it can build. It closes and its shares are worthless",
    );
  });
});
