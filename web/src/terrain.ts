/**
 * Decoration layout for terrain hexes. The server only says which hexes are asteroid fields or
 * nebulae; the rocks and wisps drawn on them are cosmetic, so they are scattered here from the
 * hex coordinates. That keeps the same hex looking the same on every render and every reload.
 */

import type { Axial } from "./api";

export interface Blob {
  /** Offset from the hex center. */
  x: number;
  y: number;
  r: number;
}

export interface ScatterOptions {
  count: number;
  /** Radius of the disc around the hex center that every blob must stay inside. */
  area: number;
  minRadius: number;
  maxRadius: number;
  /** Distinguishes layers (rocks, wisps) drawn on the same hex. */
  salt: number;
  /** Whether blobs may overlap; haze wisps should, rocks should not. */
  overlap: boolean;
}

const ROCK_GAP = 0.8;
const ATTEMPTS_PER_BLOB = 40;

/** A small deterministic random generator (mulberry32), so a hex always scatters the same way. */
function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hexSeed(hex: Axial, salt: number): number {
  return (Math.imul(hex[0], 73856093) ^ Math.imul(hex[1], 19349663) ^ Math.imul(salt, 83492791)) >>> 0;
}

/**
 * Up to `count` circles scattered inside a disc around the hex center. Fewer come back when the
 * disc is too crowded to fit them without overlapping.
 */
export function scatterBlobs(hex: Axial, options: ScatterOptions): Blob[] {
  const { count, area, minRadius, maxRadius, salt, overlap } = options;
  const random = seededRandom(hexSeed(hex, salt));
  const blobs: Blob[] = [];
  for (let attempt = 0; attempt < count * ATTEMPTS_PER_BLOB && blobs.length < count; attempt += 1) {
    const r = minRadius + random() * (maxRadius - minRadius);
    const distance = Math.sqrt(random()) * (area - r);
    const angle = random() * 2 * Math.PI;
    const candidate = { x: distance * Math.cos(angle), y: distance * Math.sin(angle), r };
    const clear = blobs.every((b) => Math.hypot(b.x - candidate.x, b.y - candidate.y) >= b.r + r + ROCK_GAP);
    if (overlap || clear) blobs.push(candidate);
  }
  return blobs;
}
