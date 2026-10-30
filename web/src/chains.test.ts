import { describe, expect, it } from "vitest";
import type { GameState, Revenue, RevenueChain, RevenuePair } from "./api";
import {
  chainKind,
  chainOfLink,
  chainPath,
  chainStory,
  chainSum,
  demandedCorporations,
  listText,
  middleStops,
  revenueChains,
  surrenderChoice,
} from "./chains";
import { corporation, gameState, logEntry, planetFacilities, withFacilities } from "./playback/fixtures";
import { operatingQueue } from "./selectors";

function link(a: string, b: string, value: number, contract = false): RevenuePair {
  return { a, b, value, typed: true, contract };
}

/** Kessel's raw goods to Sullust's industry, on to Corellia's shipyards, and to the site. */
const CARGO: RevenueChain = {
  stops: ["Kessel", "Sullust", "Corellia", "Death Star"],
  links: [link("Kessel", "Sullust", 30), link("Sullust", "Corellia", 30), link("Corellia", "Death Star", 60, true)],
  regional: 20,
  value: 140,
};
const BASIC: RevenueChain = {
  stops: ["Naboo", "Ryloth"],
  links: [{ a: "Naboo", b: "Ryloth", value: 5, typed: false, contract: false }],
  regional: 0,
  value: 5,
};

describe("the cargo story", () => {
  it("reads a chain in travel order with each link and its regional bonus", () => {
    expect(chainPath(CARGO)).toBe("Kessel → Sullust → Corellia → Death Star");
    expect(chainSum(CARGO)).toBe("30 + 30 + 60 + 20 regional");
    expect(chainStory(CARGO)).toBe("Kessel → Sullust → Corellia → Death Star · 30 + 30 + 60 + 20 regional");
    expect(middleStops(CARGO)).toEqual(["Sullust", "Corellia"]);
  });

  it("reads a basic route as one link", () => {
    expect(chainStory(BASIC)).toBe("Naboo → Ryloth · 5");
    expect(middleStops(BASIC)).toEqual([]);
  });

  it("calls a chain a contract when it delivers to the site, else typed only if every link is", () => {
    expect(chainKind(CARGO)).toBe("contract");
    expect(chainKind(BASIC)).toBe("basic");
    expect(chainKind({ ...CARGO, links: CARGO.links.slice(0, 2) })).toBe("typed");
  });

  it("finds the chain a map arc's link belongs to", () => {
    const revenue: Revenue = { total: 145, pairs: [...CARGO.links, ...BASIC.links], chains: [CARGO, BASIC] };
    expect(chainOfLink(revenue, link("Sullust", "Corellia", 30))).toBe(CARGO);
    expect(chainOfLink(revenue, link("Corellia", "Sullust", 30))).toBeNull();
  });

  it("reads each pair as a two-stop chain under the pair rules", () => {
    const pair = link("Kuat", "Corellia", 40);
    expect(revenueChains({ total: 40, pairs: [pair], chains: [] })).toEqual([
      { stops: ["Kuat", "Corellia"], links: [pair], regional: 0, value: 40 },
    ]);
    expect(revenueChains({ total: 145, pairs: CARGO.links, chains: [CARGO] })).toEqual([CARGO]);
  });

  it("lists names in prose", () => {
    expect(listText(["CEC"])).toBe("CEC");
    expect(listText(["CEC", "KDY"])).toBe("CEC and KDY");
    expect(listText(["CEC", "KDY", "KTG"])).toBe("CEC, KDY and KTG");
  });
});

/** A seizure under the chain rules after OR1.2: KDY chooses, then CEC. */
function surrendering(overrides: Partial<GameState> = {}): GameState {
  const base = withFacilities(
    gameState({
      phase: "surrender",
      roundLabel: "OR1.2",
      currentPlayer: "P3",
      currentCorporation: "KDY",
      corporations: [
        corporation("CEC", { status: "floated", president: "P1", fleets: 1 }),
        corporation("KDY", { status: "floated", president: "P3", fleets: 2, revenue: { total: 90, pairs: [], chains: [] } }),
      ],
      log: [
        logEntry(10, "Empire", "demands a facility from KTG, KDY, CEC", "OR1.2"),
        logEntry(11, "Empire", "takes over KTG's facility at Kashyyyk; it owns 1", "OR1.2"),
      ],
    }),
    [
      planetFacilities("Kuat", [-3, 2], { facilities: [{ owner: "KDY", build: 1 }] }),
      planetFacilities("Sullust", [1, 3], { facilities: [{ owner: "KDY", build: 2 }] }),
    ],
  );
  return {
    ...base,
    facilities: {
      ...base.facilities!,
      surrenderQueue: ["KDY", "CEC"],
      surrenderOptions: [
        { action: { type: "surrender_facility", planet: [1, 3] }, name: "Sullust", revenue: 30 },
        { action: { type: "surrender_facility", planet: [-3, 2] }, name: "Kuat", revenue: 60 },
      ],
    },
    ...overrides,
  };
}

describe("surrender choices", () => {
  it("orders the options by the revenue lost and names who chooses next", () => {
    const choice = surrenderChoice(surrendering())!;
    expect(choice.corp.id).toBe("KDY");
    expect(choice.options.map((o) => [o.name, o.revenue, o.loss])).toEqual([
      ["Kuat", 60, 30],
      ["Sullust", 30, 60],
    ]);
    expect(choice.waiting).toEqual(["CEC"]);
  });

  it("offers nothing outside a surrender phase, or for a corporation the options are not for", () => {
    expect(surrenderChoice(surrendering({ phase: "network" }))).toBeNull();
    expect(surrenderChoice(surrendering({ currentCorporation: "CEC" }))!.options).toEqual([]);
  });

  it("takes the seizure's corporations from the Empire's demand", () => {
    expect(demandedCorporations(surrendering())).toEqual(["KTG", "KDY", "CEC"]);
    expect(demandedCorporations(surrendering({ log: [] }))).toEqual(["KDY", "CEC"]);
  });

  it("puts the seizure in the operating rail, with who has chosen", () => {
    expect(operatingQueue(surrendering()).map((e) => [e.corpId, e.stage, e.log.map((l) => l.text)])).toEqual([
      ["KTG", "done", ["takes over KTG's facility at Kashyyyk; it owns 1"]],
      ["KDY", "current", []],
      ["CEC", "upcoming", []],
    ]);
  });
});
