import { describe, expect, it } from "vitest";
import type { Axial, Planet } from "./api";
import {
  DIRECTIONS,
  assignRegions,
  badgeText,
  edgeEndpoints,
  edgeMidpoint,
  hexCorners,
  hexDistance,
  hexKey,
  hexToPixel,
  neighbor,
} from "./hex";

const SIZE = 10;

function boardHexes(radius: number): Axial[] {
  const hexes: Axial[] = [];
  for (let q = -radius; q <= radius; q++) {
    for (let r = -radius; r <= radius; r++) {
      if (Math.max(Math.abs(q), Math.abs(r), Math.abs(q + r)) <= radius) hexes.push([q, r]);
    }
  }
  return hexes;
}

describe("hexToPixel", () => {
  it("places the origin at (0, 0)", () => {
    expect(hexToPixel([0, 0], SIZE)).toEqual({ x: 0, y: 0 });
  });

  it("follows the design doc formula", () => {
    const p = hexToPixel([2, 3], SIZE);
    expect(p.x).toBeCloseTo(Math.sqrt(3) * SIZE * 3.5);
    expect(p.y).toBeCloseTo(45);
  });
});

describe("edgeMidpoint", () => {
  it.each(DIRECTIONS)("points from the center toward the %s neighbor, halfway", (direction) => {
    const center = hexToPixel([0, 0], SIZE);
    const other = hexToPixel(neighbor([0, 0], direction), SIZE);
    const mid = edgeMidpoint(direction, SIZE);
    expect(center.x + mid.x).toBeCloseTo((center.x + other.x) / 2);
    expect(center.y + mid.y).toBeCloseTo((center.y + other.y) / 2);
  });

  it("puts the E edge on the right side", () => {
    const mid = edgeMidpoint("E", SIZE);
    expect(mid.x).toBeGreaterThan(0);
    expect(mid.y).toBeCloseTo(0);
  });

  it("puts the SE edge below and to the right", () => {
    const mid = edgeMidpoint("SE", SIZE);
    expect(mid.x).toBeGreaterThan(0);
    expect(mid.y).toBeGreaterThan(0);
  });
});

describe("edgeEndpoints", () => {
  it.each(DIRECTIONS)("returns two hex corners straddling the %s midpoint", (direction) => {
    const [a, b] = edgeEndpoints(direction, SIZE);
    const mid = edgeMidpoint(direction, SIZE);
    expect((a.x + b.x) / 2).toBeCloseTo(mid.x);
    expect((a.y + b.y) / 2).toBeCloseTo(mid.y);
    const corners = hexCorners(SIZE);
    for (const end of [a, b]) {
      expect(corners.some((c) => Math.hypot(c.x - end.x, c.y - end.y) < 1e-9)).toBe(true);
    }
  });
});

describe("hexCorners", () => {
  it("starts at the top corner of a pointy-top hex", () => {
    const [top] = hexCorners(SIZE);
    expect(top.x).toBeCloseTo(0);
    expect(top.y).toBeCloseTo(-SIZE);
  });
});

describe("hexDistance", () => {
  it("measures axial distance", () => {
    expect(hexDistance([0, 0], [0, 0])).toBe(0);
    expect(hexDistance([0, 0], [1, -1])).toBe(1);
    expect(hexDistance([-6, 0], [6, 0])).toBe(12);
    expect(hexDistance([-5, 3], [0, 0])).toBe(5);
  });
});

describe("board", () => {
  it("has 127 hexes at radius 6", () => {
    expect(boardHexes(6)).toHaveLength(127);
  });
});

describe("assignRegions", () => {
  const planets: Planet[] = [
    { name: "Core", hex: [-2, 0], region: "Core", tags: ["M"] },
    { name: "Outer", hex: [2, 0], region: "Outer Rim", tags: ["R"] },
    { name: "Mid", hex: [0, 2], region: "Mid Rim", tags: ["A"] },
  ];

  it("uses the nearest planet", () => {
    const regions = assignRegions([[-2, 1], [2, -1]], planets);
    expect(regions.get(hexKey([-2, 1]))).toBe("Core");
    expect(regions.get(hexKey([2, -1]))).toBe("Outer Rim");
  });

  it("breaks ties Core, then Mid Rim, then Outer Rim", () => {
    // (0, 0) is two steps from all three planets.
    expect(assignRegions([[0, 0]], planets).get(hexKey([0, 0]))).toBe("Core");
    const withoutCore = planets.slice(1);
    expect(assignRegions([[0, 0]], withoutCore).get(hexKey([0, 0]))).toBe("Mid Rim");
  });
});

describe("badgeText", () => {
  it("joins dual tags with a slash", () => {
    expect(badgeText(["I", "S"])).toBe("I/S");
    expect(badgeText(["M"])).toBe("M");
  });
});
