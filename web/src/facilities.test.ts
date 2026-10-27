import { describe, expect, it } from "vitest";
import type { BuildFacilityAction, CorporationState, GameState } from "./api";
import {
  bestGain,
  buildGain,
  buildsByPlanet,
  changedFacilityHexes,
  facilitiesOf,
  facilityChoice,
  itemCount,
  laneConnects,
  laneArrivals,
  laneOwners,
  laneHex,
  mergeFacilities,
  mergePlanets,
  planetExitsText,
  planetsByKey,
  sameBuild,
  seizedFacilities,
  seizureTarget,
  supplyItem,
} from "./facilities";
import { corporation, deathStarState, gameState, planetFacilities, withFacilities } from "./playback/fixtures";

const KUAT: [number, number] = [-3, 2];
const open: BuildFacilityAction = { type: "build_facility", planet: KUAT, cost: 60 };
const toWest: BuildFacilityAction = { type: "build_facility", planet: KUAT, exit: "W", cost: 60 };
const corellia: BuildFacilityAction = { type: "build_facility", planet: [-5, 3], cost: 60 };

function operator(overrides: Partial<CorporationState> = {}): CorporationState {
  return corporation("CEC", { status: "floated", treasury: 200, fleets: 1, revenue: { total: 40, pairs: [] }, ...overrides });
}

/** CEC in its facility step with builds at Kuat (open, or to the lane on its W side) and at Corellia. */
function facilityStep(): GameState {
  const base = withFacilities(gameState({ phase: "fleet", currentCorporation: "CEC", corporations: [operator()] }));
  return {
    ...base,
    legalActions: [open, toWest, corellia, { type: "finish_fleets" }],
    facilities: {
      ...base.facilities!,
      options: [
        { action: { ...open }, revenue: 60, reaches: [], lane: [] },
        { action: { ...toWest }, revenue: 100, reaches: ["Alderaan"], lane: ["KDY"] },
        { action: { ...corellia }, revenue: 30, reaches: [], lane: [] },
      ],
    },
  };
}

describe("supply wording", () => {
  it("names fleets or facilities from the supply", () => {
    expect(supplyItem(deathStarState())).toBe("fleet");
    expect(supplyItem(withFacilities(gameState()).deathStar)).toBe("facility");
    expect(supplyItem(undefined)).toBe("fleet");
    expect(itemCount("facility", 1)).toBe("1 facility");
    expect(itemCount("facility", 3)).toBe("3 facilities");
    expect(itemCount("fleet", 2)).toBe("2 fleets");
  });
});

describe("planet exits", () => {
  const planets = planetsByKey({
    planets: [planetFacilities("Kuat", KUAT, { exits: 2, claimed: ["NE"], unclaimed: 1, dangling: ["W"] })],
  });

  it("connects a lane only through a claimed exit, and always into an open hub", () => {
    expect(laneConnects(planets, "-3,2", "NE")).toBe(true);
    expect(laneConnects(planets, "-3,2", "W")).toBe(false);
    expect(laneConnects(planets, "6,-2", "W")).toBe(true);
  });

  it("describes a planet's exits, facilities and dangling lanes", () => {
    const kuat = planetFacilities("Kuat", KUAT, {
      exits: 2,
      claimed: ["NE"],
      unclaimed: 1,
      dangling: ["W"],
      facilities: [{ owner: "KDY", build: 1 }],
      freeSlots: 1,
    });
    expect(planetExitsText(kuat)).toBe(
      "2 exits (NE claimed, 1 open); facilities: KDY; 1 facility slot free; a lane dangles on its W side",
    );
    expect(planetExitsText(planetFacilities("Hoth", [0, 0], { unclaimed: 0, claimed: ["E"], freeSlots: 0 }))).toBe(
      "1 exit (E claimed); 0 facility slots free",
    );
  });
});

describe("merging move frames", () => {
  it("replaces changed planets by hex and keeps the rest", () => {
    const base = [planetFacilities("Corellia", [-5, 3]), planetFacilities("Kuat", KUAT)];
    const kuat = planetFacilities("Kuat", KUAT, { exits: 2, unclaimed: 2, facilities: [{ owner: "CEC", build: 2 }] });
    expect(mergePlanets(base, [kuat])).toEqual([base[0], kuat]);
    expect(mergePlanets(base, [])).toBe(base);
  });

  it("takes the frame's seizure targets and drops the options", () => {
    const state = facilityStep().facilities!;
    const merged = mergeFacilities(state, { perPlanet: 2, planets: [], seizureTargets: [{ corp: "CEC", hex: [-5, 3] }] });
    expect(merged).toEqual({ ...state, seizureTargets: [{ corp: "CEC", hex: [-5, 3] }], options: [] });
    expect(mergeFacilities(state, undefined)).toBe(state);
  });
});

describe("the facility step", () => {
  it("groups the legal builds by planet with the server's previews", () => {
    const builds = buildsByPlanet(facilityStep());
    expect([...builds.keys()]).toEqual(["-3,2", "-5,3"]);
    expect(builds.get("-3,2")!.map((b) => b.action)).toEqual([open, toWest]);
    expect(builds.get("-3,2")![1].preview).toMatchObject({ revenue: 100, reaches: ["Alderaan"] });
  });

  it("submits the legal action itself, not the preview's copy", () => {
    const state = facilityStep();
    const [first] = buildsByPlanet(state).get("-3,2")!;
    expect(first.action).toBe(state.legalActions[0]);
    expect(sameBuild(first.action, state.facilities!.options[0].action)).toBe(true);
    expect(sameBuild(open, toWest)).toBe(false);
  });

  it("says what each build adds to this turn's revenue", () => {
    const corp = operator();
    const builds = buildsByPlanet(facilityStep());
    expect(builds.get("-3,2")!.map((b) => buildGain(b, corp))).toEqual([20, 60]);
    expect(bestGain(builds.get("-3,2")!, corp)).toBe(60);
    expect(bestGain(builds.get("-5,3")!, corp)).toBe(0);
    expect(buildGain({ action: open, preview: null }, corp)).toBe(0);
  });

  it("finds the lane a build gives its exit to", () => {
    expect(laneHex(toWest)).toEqual([-4, 2]);
    expect(laneHex(open)).toBeNull();
  });

  it("collects the finish, and whether a facility is still needed", () => {
    const state = facilityStep();
    const choice = facilityChoice(state, operator());
    expect(choice.finish).toEqual({ type: "finish_fleets" });
    expect(choice.mandatory).toBe(false);
    expect(choice.atLimit).toBe(false);
    expect(facilityChoice(state, operator({ fleets: 0 })).mandatory).toBe(true);
    expect(facilityChoice(state, operator({ fleets: 4 })).atLimit).toBe(true);
  });
});

describe("ownership and seizures", () => {
  const before = withFacilities(gameState()).facilities!;
  const corellia = before.planets[0];
  const seized = {
    ...before,
    planets: [{ ...corellia, facilities: [{ owner: "Empire", build: 0 }] }],
    seizureTargets: [],
  };

  it("lists a corporation's facilities and the one the next seizure takes", () => {
    expect(facilitiesOf(before, "CEC").map((p) => p.name)).toEqual(["Corellia"]);
    const state = { facilities: { ...before, seizureTargets: [{ corp: "CEC", hex: corellia.hex }] } };
    expect(seizureTarget(state, "CEC")?.name).toBe("Corellia");
    expect(seizureTarget(state, "KDY")).toBeNull();
    expect(seizureTarget({}, "CEC")).toBeNull();
  });

  it("finds facilities that turned Imperial, even from a frame listing only changed planets", () => {
    expect(seizedFacilities(before, seized)).toEqual([{ corp: "CEC", planet: "Corellia", hex: corellia.hex }]);
    expect(seizedFacilities(seized, seized)).toEqual([]);
    expect(seizedFacilities(undefined, seized)).toEqual([]);
  });

  it("outlines planets with a new facility in the builder's colour, and seizures neutrally", () => {
    const kuat = { ...before.planets[1], facilities: [{ owner: "KDY", build: 3 }] };
    const built = { ...before, planets: [corellia, kuat] };
    expect(changedFacilityHexes(before, built)).toEqual(new Map([["-3,2", ["KDY"]]]));
    expect(changedFacilityHexes(before, seized)).toEqual(new Map([["-5,3", []]]));
    expect(changedFacilityHexes(before, before).size).toBe(0);
    expect(changedFacilityHexes(undefined, undefined).size).toBe(0);
  });
});

describe("lanes arriving at planets", () => {
  const facilities = {
    planets: [
      planetFacilities("Kuat", KUAT, { exits: 1, claimed: ["NE"], unclaimed: 0 }),
      planetFacilities("Corellia", [-5, 3], { exits: 2, unclaimed: 2 }),
    ],
  };

  it("claims an open exit, or dangles when the planet has none", () => {
    // (-4, 2) sits between Corellia (to its SW) and Kuat (to its E).
    const chart = { type: "chart" as const, hex: [-4, 2] as [number, number], exits: ["SW", "E"] as ("SW" | "E")[], cost: 60 };
    expect(laneArrivals(chart, facilities)).toEqual([
      { planet: "Corellia", claims: true },
      { planet: "Kuat", claims: false },
    ]);
    const upgrade = { type: "upgrade" as const, hex: [-4, 2] as [number, number], exit: "E" as const, cost: 80 };
    expect(laneArrivals(upgrade, facilities)).toEqual([{ planet: "Kuat", claims: false }]);
  });

  it("says nothing for service, or without the facility rules", () => {
    expect(laneArrivals({ type: "service", hex: [-4, 2], cost: 60 }, facilities)).toEqual([]);
    expect(laneArrivals({ type: "upgrade", hex: [-4, 2], exit: "E", cost: 80 }, undefined)).toEqual([]);
  });
});

describe("lane owners", () => {
  it("says whose lane a build connects, from the builder's side", () => {
    expect(laneOwners(["CEC"], "CEC")).toBe("your lane");
    expect(laneOwners(["KDY"], "CEC")).toBe("KDY's lane");
    expect(laneOwners(["CEC", "KDY"], "CEC")).toBe("a lane you share with KDY");
    expect(laneOwners(["CSC", "KDY"], "CEC")).toBe("a lane CSC and KDY serve");
    expect(laneOwners([], "CEC")).toBe("a lane nobody serves");
  });
});
