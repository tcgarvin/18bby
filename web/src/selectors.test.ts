import { describe, expect, it } from "vitest";
import type {
  ChartAction,
  CorporationState,
  GameConfig,
  GameState,
  LogEntry,
  PlayerState,
  ServiceAction,
  TerrainHex,
} from "./api";
import {
  dividendSplit,
  hexActionsByKey,
  nearestCellWithPrice,
  operatingQueue,
  phaseSteps,
  terrainByKey,
} from "./selectors";

describe("terrainByKey", () => {
  it("keys each terrain hex by its hexKey", () => {
    const terrain: TerrainHex[] = [
      { hex: [2, -1], kind: "asteroid" },
      { hex: [0, 3], kind: "nebula" },
    ];
    const byKey = terrainByKey(terrain);
    expect(byKey.get("2,-1")).toBe("asteroid");
    expect(byKey.get("0,3")).toBe("nebula");
  });

  it("leaves plain space absent", () => {
    expect(terrainByKey([{ hex: [1, 1], kind: "nebula" }]).has("0,0")).toBe(false);
    expect(terrainByKey([]).size).toBe(0);
  });
});

describe("hexActionsByKey", () => {
  it("keeps each action's own cost, so a nebula chart can cost more than a plain one", () => {
    const plain: ChartAction = { type: "chart", hex: [1, 0], exits: ["E", "W"], cost: 50 };
    const nebula: ChartAction = { type: "chart", hex: [2, 0], exits: ["E", "W"], cost: 80 };
    const service: ServiceAction = { type: "service", hex: [2, 0], cost: 50 };
    const byKey = hexActionsByKey([plain, nebula, service, { type: "pass" }]);
    expect(byKey.get("1,0")?.map((a) => a.cost)).toEqual([50]);
    expect(byKey.get("2,0")?.map((a) => a.cost)).toEqual([80, 50]);
  });
});

function corporation(id: string, overrides: Partial<CorporationState> = {}): CorporationState {
  return {
    id,
    name: id,
    homeworld: "",
    status: "floated",
    par: 80,
    ipoPrice: 80,
    price: 80,
    marketCell: [0, 0],
    dividendPreview: null,
    treasury: 0,
    ipoShares: 0,
    poolShares: 0,
    president: "",
    lastRevenue: 0,
    fleets: 0,
    reachablePlanets: [],
    revenue: { total: 0, pairs: [] },
    ...overrides,
  };
}

function player(id: string, shares: Record<string, number>): PlayerState {
  return { id, name: id, cash: 0, worth: 0, shares, isBot: false, difficulty: "", plan: "", certificates: 0 };
}

function gameState(overrides: Partial<GameState>): GameState {
  return {
    phase: "network",
    roundLabel: "OR2.1",
    roundNumber: 1,
    totalRounds: 6,
    currentPlayer: null,
    currentCorporation: null,
    waitingOnHuman: false,
    legalActions: [],
    players: [],
    priorityPlayer: "",
    corporations: [],
    operatingOrder: [],
    tiles: [],
    terrain: [],
    stockMarket: [],
    parColumn: 0,
    networkActionsTaken: 0,
    canUndo: false,
    automaticLogStart: 0,
    config: { sharesPerCorporation: 10 } as GameConfig,
    log: [],
    moves: [],
    ...overrides,
  };
}

function line(seq: number, round: string, actor: string, text: string): LogEntry {
  return { seq, round, actor, text };
}

describe("phaseSteps", () => {
  it("lights the stock round and its operating rounds in order", () => {
    expect(phaseSteps("SR4", 2, 6)).toEqual([
      { label: "SR4", stage: "current" },
      { label: "OR4.1", stage: "upcoming" },
      { label: "OR4.2", stage: "upcoming" },
    ]);
    expect(phaseSteps("OR4.2", 2, 6).map((s) => s.stage)).toEqual(["done", "done", "current"]);
  });

  it("marks every step done at the end of the game", () => {
    expect(phaseSteps("end", 2, 6)).toEqual([
      { label: "SR6", stage: "done" },
      { label: "OR6.1", stage: "done" },
      { label: "OR6.2", stage: "done" },
    ]);
  });
});

describe("operatingQueue", () => {
  it("splits the server's fixed order around the operating corporation", () => {
    const state = gameState({
      phase: "network",
      currentCorporation: "CSC",
      operatingOrder: ["KTG", "KDY", "CSC", "CEC"],
      log: [
        line(1, "SR2", "Tim", "passes"),
        line(2, "OR2.1", "KTG", "charts (1,0) for 20"),
        line(3, "OR2.1", "KTG", "withholds 30; price 70"),
        line(4, "OR2.1", "KDY", "takes no network action"),
        line(5, "OR2.1", "KDY", "pays 100 (10/share); price 120"),
      ],
    });
    const queue = operatingQueue(state);
    expect(queue.map((e) => [e.corpId, e.stage])).toEqual([
      ["KTG", "done"],
      ["KDY", "done"],
      ["CSC", "current"],
      ["CEC", "upcoming"],
    ]);
    expect(queue[0].log.map((e) => e.text)).toEqual(["charts (1,0) for 20", "withholds 30; price 70"]);
  });

  it("shows only this round's lines", () => {
    const state = gameState({
      roundLabel: "OR2.2",
      currentCorporation: "KDY",
      operatingOrder: ["CEC", "KDY"],
      log: [line(1, "OR2.1", "CEC", "pays 50 (5/share); price 90"), line(2, "OR2.2", "CEC", "withholds 20; price 80")],
    });
    const queue = operatingQueue(state);
    expect(queue.map((e) => e.stage)).toEqual(["done", "current"]);
    expect(queue[0].log.map((e) => e.seq)).toEqual([2]);
  });

  it("is empty outside operating rounds", () => {
    expect(operatingQueue(gameState({ phase: "stock" }))).toEqual([]);
  });
});

describe("dividendSplit", () => {
  it("pays held shares the floored per-share amount and leaves the rest with the bank", () => {
    const corp = corporation("CEC", { ipoShares: 2, poolShares: 1 });
    const state = gameState({
      corporations: [corp],
      players: [player("a", { CEC: 5 }), player("b", { CEC: 2 }), player("c", {})],
    });
    const split = dividendSplit(state, corp, 125);
    expect(split.perShare).toBe(12);
    expect(split.payouts.map((p) => p.amount)).toEqual([60, 24, 0]);
    expect(split.bankKeeps).toBe(41);
  });
});

describe("nearestCellWithPrice", () => {
  const market = [
    [80, 90, 100, 110],
    [70, 80, 90, 100],
  ];
  it("prefers the same row over an equal price diagonally", () => {
    expect(nearestCellWithPrice(market, [1, 1], 90)).toEqual([1, 2]);
    expect(nearestCellWithPrice(market, [0, 3], 110)).toEqual([0, 3]);
  });
  it("finds a price that only exists in another row", () => {
    expect(nearestCellWithPrice(market, [1, 3], 110)).toEqual([0, 3]);
    expect(nearestCellWithPrice(market, [0, 0], 5)).toBeNull();
  });
});
