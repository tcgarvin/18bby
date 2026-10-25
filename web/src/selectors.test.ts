import { describe, expect, it } from "vitest";
import type { ChartAction, ServiceAction, TerrainHex } from "./api";
import { hexActionsByKey, terrainByKey } from "./selectors";

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
