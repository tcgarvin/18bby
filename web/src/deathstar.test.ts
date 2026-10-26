import { describe, expect, it } from "vitest";
import type { CorporationState } from "./api";
import {
  fleetChoice,
  gameEnd,
  pairUsage,
  pairUsageText,
  pendingStages,
  resultText,
  seizureRisk,
  siteHexes,
  sitePlanet,
  stageCubes,
  stageProgress,
  supplyText,
} from "./deathstar";
import { corporation, deathStarState, gameState, trackAt } from "./playback/fixtures";

function operator(overrides: Partial<CorporationState> = {}): CorporationState {
  return corporation("CEC", {
    status: "floated",
    treasury: 200,
    fleets: 1,
    revenue: { total: 70, pairs: [{ a: "Corellia", b: "Kuat", value: 70, typed: true, contract: false }] },
    fleetRevenue: { withNextFleet: 110, uncapped: 130, uncappedPairs: 3 },
    ...overrides,
  });
}

describe("sites", () => {
  it("draws the active site as a hub tagged W", () => {
    expect(sitePlanet(deathStarState())).toEqual({ name: "Death Star", hex: [6, -2], region: "Outer Rim", tags: ["W"] });
    expect(siteHexes(deathStarState(), "reserved")).toEqual([[-1, 5]]);
  });

  it("has no hub once the station has launched, or without the rules", () => {
    const launched = deathStarState({
      launched: true,
      sites: [
        { hex: [6, -2], region: "Outer Rim", status: "vacated" },
        { hex: [-1, 5], region: "Mid Rim", status: "launched" },
      ],
    });
    expect(sitePlanet(launched)).toBeNull();
    expect(siteHexes(launched, "vacated")).toEqual([[6, -2]]);
    expect(sitePlanet(undefined)).toBeNull();
    expect(siteHexes(undefined, "reserved")).toEqual([]);
  });
});

describe("the track", () => {
  it("counts cubes per stage, carrying extra cubes over", () => {
    const track = trackAt(deathStarState(), 8, 1);
    expect([0, 1, 2, 3].map((i) => stageCubes(track, i))).toEqual([6, 2, 0, 0]);
    expect(stageProgress(track)).toMatchObject({ index: 1, cubes: 2, toFill: 4 });
    expect(stageProgress(track).stage?.name).toBe("Superstructure");
  });

  it("lists a filled stage as pending until the round ends", () => {
    const filled = trackAt(deathStarState(), 6, 0);
    expect(pendingStages(filled).map((s) => s.name)).toEqual(["Frame"]);
    expect(stageProgress(filled).toFill).toBe(0);
    expect(pendingStages(trackAt(deathStarState(), 6, 1))).toEqual([]);
  });

  it("says what each result does, naming where the site moves", () => {
    const track = deathStarState();
    expect(resultText("seizure", track)).toMatch(/every corporation with a fleet loses one/);
    expect(resultText("move", track)).toBe("The site moves to the Mid Rim");
    expect(resultText("completion", track)).toMatch(/game ends after this round/);
  });

  it("ends at the backstop unless the station launched", () => {
    expect(gameEnd(deathStarState())).toEqual({ round: 8, reason: "backstop" });
    expect(gameEnd(deathStarState({ launched: true, finalRound: 5 }))).toEqual({ round: 5, reason: "launch" });
  });
});

describe("the fleet supply", () => {
  it("says how many are left at this price and what comes next", () => {
    expect(supplyText(deathStarState())).toBe("6 left at 60, then 90");
    const last = deathStarState();
    last.fleets = { ...last.fleets, price: 160, tier: 3, remainingInTier: "unlimited" };
    expect(supplyText(last)).toBe("160 each, unlimited");
  });
});

describe("fleetChoice", () => {
  it("takes Buy and Finish from the legal actions and says what the next fleet adds", () => {
    const state = gameState({
      phase: "fleet",
      deathStar: deathStarState(),
      legalActions: [{ type: "buy_fleet", cost: 60 }, { type: "finish_fleets" }],
    });
    const choice = fleetChoice(state, operator());
    expect(choice.buy).toEqual({ type: "buy_fleet", cost: 60 });
    expect(choice.finish).toEqual({ type: "finish_fleets" });
    expect(choice.adds).toBe(40);
    expect(choice.mandatory).toBe(false);
    expect(choice.atLimit).toBe(false);
  });

  it("knows a corporation with no fleet must buy one, and one at the limit cannot", () => {
    const state = gameState({ phase: "fleet", deathStar: deathStarState(), legalActions: [{ type: "buy_fleet", cost: 60 }] });
    expect(fleetChoice(state, operator({ fleets: 0 }))).toMatchObject({ mandatory: true, finish: null });
    const full = gameState({ phase: "fleet", deathStar: deathStarState(), legalActions: [{ type: "finish_fleets" }] });
    expect(fleetChoice(full, operator({ fleets: 4 }))).toMatchObject({ atLimit: true, buy: null });
  });
});

describe("seizureRisk", () => {
  it("warns a one-fleet corporation of the seizure the stage being built ends in", () => {
    const track = trackAt(deathStarState(), 4, 0);
    expect(seizureRisk(track, 1, 200)).toMatchObject({ cubesToGo: 2, covered: true, price: 60 });
    expect(seizureRisk(track, 1, 40)).toMatchObject({ covered: false });
  });

  it("is quiet with a spare fleet, or while a non-seizure stage is being built", () => {
    expect(seizureRisk(deathStarState(), 2, 0)).toBeNull();
    expect(seizureRisk(trackAt(deathStarState(), 7, 1), 1, 0)).toBeNull();
  });

  it("counts a filled seizure stage as due at the end of the round", () => {
    expect(seizureRisk(trackAt(deathStarState(), 6, 0), 1, 0)).toMatchObject({ cubesToGo: 0 });
  });
});

describe("pairUsage", () => {
  it("compares the pairs run with the pairs the network offers", () => {
    const usage = pairUsage(operator());
    expect(usage).toEqual({ run: 1, available: 3, fleets: 1 });
    expect(pairUsageText(usage!)).toBe("1 of 3 pairs run · 1 fleet");
    expect(pairUsageText({ run: 2, available: 2, fleets: 3 })).toBe("2 pairs run · 3 fleets");
  });

  it("is absent without the Death Star rules", () => {
    expect(pairUsage(corporation("CEC"))).toBeNull();
  });
});
