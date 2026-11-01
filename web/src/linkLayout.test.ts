import { describe, expect, it } from "vitest";
import type { Point } from "./hex";
import { layoutLinks, type LinkGeometry } from "./linkLayout";

const GEOMETRY: LinkGeometry = {
  hexSide: 34,
  badgeRadius: 12,
  pillHalfWidth: 13,
  pillHalfHeight: 8,
  nameOffset: 20,
  nameHalfWidth: 30,
  nameHalfHeight: 7,
};

function pointOnArc(from: Point, control: Point, to: Point, t: number): Point {
  const u = 1 - t;
  return { x: u * u * from.x + 2 * u * t * control.x + t * t * to.x, y: u * u * from.y + 2 * u * t * control.y + t * t * to.y };
}

function closestApproach(from: Point, control: Point, to: Point, target: Point): number {
  const distances = Array.from({ length: 101 }, (_, i) => {
    const point = pointOnArc(from, control, to, i / 100);
    return Math.hypot(point.x - target.x, point.y - target.y);
  });
  return Math.min(...distances);
}

describe("layoutLinks", () => {
  it("keeps the default shallow arc and centred pill when nothing is in the way", () => {
    const from = { x: 0, y: 0 };
    const to = { x: 200, y: 0 };
    const layout = layoutLinks([{ key: "a-b", from, to }], [from, to], GEOMETRY).get("a-b");
    expect(layout?.control).toEqual({ x: 100, y: 36 });
    expect(layout?.label).toEqual({ x: 100, y: 18 });
  });

  it("swings an arc around a planet it does not stop at", () => {
    const from = { x: 0, y: 0 };
    const to = { x: 200, y: 0 };
    const between = { x: 100, y: 18 };
    const layout = layoutLinks([{ key: "a-b", from, to }], [from, to, between], GEOMETRY).get("a-b");
    if (layout === undefined) throw new Error("link was not laid out");
    expect(closestApproach(from, layout.control, to, between)).toBeGreaterThan(GEOMETRY.badgeRadius);
  });

  it("does not stack the pills of links that share a midpoint", () => {
    const links = [
      { key: "a-b", from: { x: 0, y: 0 }, to: { x: 200, y: 0 } },
      { key: "c-d", from: { x: 0, y: 8 }, to: { x: 200, y: 8 } },
    ];
    const hubs = links.flatMap((link) => [link.from, link.to]);
    const layouts = layoutLinks(links, hubs, GEOMETRY);
    const [first, second] = links.map((link) => layouts.get(link.key)?.label);
    if (first === undefined || second === undefined) throw new Error("links were not laid out");
    const apart =
      Math.abs(first.x - second.x) > 2 * GEOMETRY.pillHalfWidth || Math.abs(first.y - second.y) > 2 * GEOMETRY.pillHalfHeight;
    expect(apart).toBe(true);
  });

  it("gives the same layout whatever order the links arrive in", () => {
    const links = [
      { key: "a-b", from: { x: 0, y: 0 }, to: { x: 200, y: 0 } },
      { key: "c-d", from: { x: 40, y: -60 }, to: { x: 120, y: 90 } },
    ];
    const hubs = links.flatMap((link) => [link.from, link.to]);
    expect(layoutLinks(links, hubs, GEOMETRY)).toEqual(layoutLinks([...links].reverse(), hubs, GEOMETRY));
  });
});
