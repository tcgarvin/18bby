import { describe, expect, it } from "vitest";
import type { LogEntry } from "./api";
import { newLogEntries } from "./logdiff";

const entry = (n: number): LogEntry => ({ seq: n, round: "SR1", actor: "P1", text: `e${n}` });
const range = (from: number, to: number): LogEntry[] =>
  Array.from({ length: to - from }, (_, i) => entry(from + i));

describe("newLogEntries", () => {
  it("returns appended entries", () => {
    expect(newLogEntries(range(0, 3), range(0, 5))).toEqual(range(3, 5));
  });

  it("returns nothing when unchanged", () => {
    expect(newLogEntries(range(0, 3), range(0, 3))).toEqual([]);
  });

  it("handles a truncated window", () => {
    expect(newLogEntries(range(0, 200), range(5, 205))).toEqual(range(200, 205));
  });

  it("treats everything as new when there is no previous log", () => {
    expect(newLogEntries([], range(0, 2))).toEqual(range(0, 2));
  });
});
