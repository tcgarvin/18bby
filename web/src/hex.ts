/**
 * Pointy-top axial hex geometry, matching docs/design/hex-map-design.md and
 * src/bby18/hexgrid.py. Screen y increases downward.
 */

import type { Axial, DirectionName, Planet, Region } from "./api";
import { REGIONS } from "./api";

export const DIRECTIONS: DirectionName[] = ["E", "SE", "SW", "W", "NW", "NE"];

export const DIRECTION_DELTAS: Record<DirectionName, Axial> = {
  E: [1, 0],
  SE: [0, 1],
  SW: [-1, 1],
  W: [-1, 0],
  NW: [0, -1],
  NE: [1, -1],
};

export interface Point {
  x: number;
  y: number;
}

export function hexKey(hex: Axial): string {
  return `${hex[0]},${hex[1]}`;
}

export function sameHex(a: Axial, b: Axial): boolean {
  return a[0] === b[0] && a[1] === b[1];
}

export function neighbor(hex: Axial, direction: DirectionName): Axial {
  const [dq, dr] = DIRECTION_DELTAS[direction];
  return [hex[0] + dq, hex[1] + dr];
}

export function hexDistance(a: Axial, b: Axial): number {
  const dq = b[0] - a[0];
  const dr = b[1] - a[1];
  return Math.max(Math.abs(dq), Math.abs(dr), Math.abs(dq + dr));
}

/** Pixel center of a hex with side length `size`, relative to the center of (0, 0). */
export function hexToPixel(hex: Axial, size: number): Point {
  const [q, r] = hex;
  return { x: Math.sqrt(3) * size * (q + r / 2), y: 1.5 * size * r };
}

/** Angle in degrees (clockwise from +x, y down) of direction `d`'s edge midpoint. */
export function edgeAngle(direction: DirectionName): number {
  return DIRECTIONS.indexOf(direction) * 60;
}

/** Offset from a hex center to the midpoint of the edge facing `direction`. */
export function edgeMidpoint(direction: DirectionName, size: number): Point {
  const apothem = (Math.sqrt(3) / 2) * size;
  const radians = (edgeAngle(direction) * Math.PI) / 180;
  return { x: apothem * Math.cos(radians), y: apothem * Math.sin(radians) };
}

/** Corner offsets of a pointy-top hex, starting at the top corner and going clockwise. */
export function hexCorners(size: number): Point[] {
  return [0, 1, 2, 3, 4, 5].map((i) => {
    const radians = ((i * 60 - 90) * Math.PI) / 180;
    return { x: size * Math.cos(radians), y: size * Math.sin(radians) };
  });
}

export function cornersToPath(center: Point, size: number): string {
  return (
    hexCorners(size)
      .map((c, i) => `${i === 0 ? "M" : "L"}${(center.x + c.x).toFixed(2)},${(center.y + c.y).toFixed(2)}`)
      .join("") + "Z"
  );
}

/**
 * Endpoints of the edge facing `direction`, as offsets from the hex center. The two corners
 * sit 30 degrees either side of the edge midpoint's angle.
 */
export function edgeEndpoints(direction: DirectionName, size: number): [Point, Point] {
  const mid = edgeAngle(direction);
  const corner = (deg: number): Point => {
    const radians = (deg * Math.PI) / 180;
    return { x: size * Math.cos(radians), y: size * Math.sin(radians) };
  };
  return [corner(mid - 30), corner(mid + 30)];
}

/**
 * Region of every hex: the region of its nearest planet by hex distance, with ties broken in
 * the order Core, Mid Rim, Outer Rim.
 */
export function assignRegions(hexes: Axial[], planets: Planet[]): Map<string, Region> {
  const regions = new Map<string, Region>();
  for (const hex of hexes) {
    let best: { distance: number; rank: number; region: Region } | null = null;
    for (const planet of planets) {
      const distance = hexDistance(hex, planet.hex);
      const rank = REGIONS.indexOf(planet.region);
      if (best === null || distance < best.distance || (distance === best.distance && rank < best.rank)) {
        best = { distance, rank, region: planet.region };
      }
    }
    if (best === null) {
      throw new Error("assignRegions needs at least one planet");
    }
    regions.set(hexKey(hex), best.region);
  }
  return regions;
}

/** Planet type badge text, e.g. ["I", "S"] becomes "I/S". Tags keep the engine's order. */
export function badgeText(tags: string[]): string {
  return tags.join("/");
}
