import { describe, expect, it } from "vitest";
import type { TileState } from "./api";
import { changedHexes } from "./tilediff";

const tile = (q: number, r: number, exits: TileState["exits"], service: string[]): TileState => ({
  hex: [q, r],
  exits,
  service,
});

describe("changedHexes", () => {
  it("reports new tiles with the corporations serving them", () => {
    const result = changedHexes([], [tile(0, 0, ["E", "W"], ["CEC"])]);
    expect([...result]).toEqual([["0,0", ["CEC"]]]);
  });

  it("reports only newly gained service on an existing tile", () => {
    const before = [tile(1, 0, ["E", "W"], ["CEC"])];
    const after = [tile(1, 0, ["E", "W"], ["CEC", "KDY"])];
    expect(changedHexes(before, after).get("1,0")).toEqual(["KDY"]);
  });

  it("reports an upgrade with no new service as an empty list", () => {
    const before = [tile(0, 1, ["E", "W"], ["CEC"])];
    const after = [tile(0, 1, ["E", "W", "NE"], ["CEC"])];
    expect(changedHexes(before, after).get("0,1")).toEqual([]);
  });

  it("ignores unchanged tiles", () => {
    const same = [tile(2, 2, ["SE"], ["CSC"])];
    expect(changedHexes(same, same).size).toBe(0);
  });
});
