import { describe, expect, it } from "vitest";
import { scatterBlobs, type ScatterOptions } from "./terrain";

const rocks: ScatterOptions = { count: 9, area: 24, minRadius: 1.2, maxRadius: 3, salt: 1, overlap: false };

describe("scatterBlobs", () => {
  it("places the same blobs for the same hex every time", () => {
    expect(scatterBlobs([3, -2], rocks)).toEqual(scatterBlobs([3, -2], rocks));
  });

  it("places different blobs on different hexes and for different salts", () => {
    expect(scatterBlobs([3, -2], rocks)).not.toEqual(scatterBlobs([-2, 3], rocks));
    expect(scatterBlobs([3, -2], rocks)).not.toEqual(scatterBlobs([3, -2], { ...rocks, salt: 2 }));
  });

  it("keeps every blob inside the area", () => {
    for (const blob of scatterBlobs([0, 0], rocks)) {
      expect(Math.hypot(blob.x, blob.y) + blob.r).toBeLessThanOrEqual(rocks.area + 1e-9);
      expect(blob.r).toBeGreaterThanOrEqual(rocks.minRadius);
      expect(blob.r).toBeLessThanOrEqual(rocks.maxRadius);
    }
  });

  it("keeps rocks apart unless overlap is allowed", () => {
    const placed = scatterBlobs([5, 5], rocks);
    expect(placed.length).toBeGreaterThan(0);
    for (const [i, a] of placed.entries()) {
      for (const b of placed.slice(i + 1)) {
        expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThan(a.r + b.r);
      }
    }
  });

  it("returns every requested blob when overlap is allowed", () => {
    expect(scatterBlobs([1, 1], { ...rocks, count: 5, overlap: true })).toHaveLength(5);
  });
});
