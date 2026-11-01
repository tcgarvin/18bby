/**
 * Where the revenue links drawn over the map go: each link is a shallow arc between two planets
 * with a value pill on it. Straight-through geometry lets an arc pass behind a planet it does not
 * stop at (so one link reads as two) and lets pills pile up, so each link picks the bow and pill
 * position that keeps clear of badges, planet names, pills and arcs already placed.
 */

import type { Point } from "./hex";

export interface LinkEnds {
  key: string;
  from: Point;
  to: Point;
}

export interface LinkLayout {
  /** Control point of the arc, a quadratic curve from `from` to `to`. */
  control: Point;
  /** Centre of the link's value pill, on the arc. */
  label: Point;
}

export interface LinkGeometry {
  /** Hex side length: the arc's bow is capped relative to it. */
  hexSide: number;
  badgeRadius: number;
  /** Half the size of a value pill. */
  pillHalfWidth: number;
  pillHalfHeight: number;
  /** A planet's name sits centred this far below its centre, this big. */
  nameOffset: number;
  nameHalfWidth: number;
  nameHalfHeight: number;
}

/** The first bow is the default; the deeper ones are there to swing around whatever is in the way. */
const BOWS = [
  { share: 0.18, capInHexes: 1.2 },
  { share: 0.3, capInHexes: 1.9 },
  { share: 0.42, capInHexes: 2.6 },
];
/** Where along the arc the pill may sit, most preferred first. */
const LABEL_POSITIONS = [0.5, 0.42, 0.58, 0.34, 0.66];
const ARC_SAMPLES = 24;
/** An arc keeps this far off a badge it does not stop at, and pills this far off anything. */
const BADGE_CLEARANCE = 5;
const PILL_MARGIN = 3;
/** Arcs closer than this run alongside each other and are hard to tell apart. */
const ARC_CROWDING = 5;

const COST_ARC_THROUGH_BADGE = 100;
const COST_PILL_ON_BADGE = 60;
const COST_PILL_ON_PILL = 60;
const COST_PILL_ON_NAME = 30;
const COST_ARC_THROUGH_NAME = 20;
const COST_ARC_THROUGH_PILL = 12;
const COST_ARC_CROWDING = 0.5;
const COST_DEEPER_BOW = 1.5;
const COST_OTHER_SIDE = 1;
const COST_LABEL_DRIFT = 8;

function along(from: Point, control: Point, to: Point, t: number): Point {
  const u = 1 - t;
  return {
    x: u * u * from.x + 2 * u * t * control.x + t * t * to.x,
    y: u * u * from.y + 2 * u * t * control.y + t * t * to.y,
  };
}

function distance(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function sampleArc(from: Point, control: Point, to: Point): Point[] {
  return Array.from({ length: ARC_SAMPLES + 1 }, (_, i) => along(from, control, to, i / ARC_SAMPLES));
}

function inBox(point: Point, center: Point, halfWidth: number, halfHeight: number): boolean {
  return Math.abs(point.x - center.x) <= halfWidth && Math.abs(point.y - center.y) <= halfHeight;
}

/**
 * Lays out `links` one at a time, longest first (they have the fewest good options), each around
 * the hubs and the links before it. The result is deterministic for the same links.
 */
export function layoutLinks(links: LinkEnds[], hubs: Point[], geometry: LinkGeometry): Map<string, LinkLayout> {
  const { hexSide, badgeRadius, pillHalfWidth, pillHalfHeight, nameOffset, nameHalfWidth, nameHalfHeight } = geometry;
  const pillWidthGap = 2 * pillHalfWidth + PILL_MARGIN;
  const pillHeightGap = 2 * pillHalfHeight + PILL_MARGIN;
  const placedArcs: { samples: Point[]; from: Point; to: Point }[] = [];
  const placedPills: Point[] = [];
  const layouts = new Map<string, LinkLayout>();
  const longestFirst = [...links].sort((a, b) => distance(b.from, b.to) - distance(a.from, a.to) || a.key.localeCompare(b.key));

  for (const { key, from, to } of longestFirst) {
    const length = distance(from, to) || 1;
    const middle = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 };
    const normal = { x: -(to.y - from.y) / length, y: (to.x - from.x) / length };
    let best: { cost: number; control: Point; label: Point; samples: Point[] } | null = null;

    for (const [bowIndex, bow] of BOWS.entries()) {
      const depth = Math.min(hexSide * bow.capInHexes, length * bow.share);
      for (const side of [1, -1]) {
        const control = { x: middle.x + normal.x * depth * side, y: middle.y + normal.y * depth * side };
        const samples = sampleArc(from, control, to);
        let arcCost = bowIndex * COST_DEEPER_BOW + (side === 1 ? 0 : COST_OTHER_SIDE);
        for (const hub of hubs) {
          // A link may leave through its own planet's name if it must, but no other link may cross it for free.
          const name = { x: hub.x, y: hub.y + nameOffset };
          if (samples.some((point) => inBox(point, name, nameHalfWidth, nameHalfHeight))) arcCost += COST_ARC_THROUGH_NAME;
          if (distance(hub, from) < 1 || distance(hub, to) < 1) continue;
          if (samples.some((point) => distance(point, hub) < badgeRadius + BADGE_CLEARANCE)) arcCost += COST_ARC_THROUGH_BADGE;
        }
        for (const pill of placedPills) {
          if (samples.some((point) => inBox(point, pill, pillHalfWidth + PILL_MARGIN, pillHalfHeight + PILL_MARGIN))) arcCost += COST_ARC_THROUGH_PILL;
        }
        for (const placed of placedArcs) {
          // Arcs meeting at a shared planet are bound to be close there: only count open space.
          const crowded = samples.filter(
            (point) =>
              distance(point, from) > badgeRadius * 2 &&
              distance(point, to) > badgeRadius * 2 &&
              placed.samples.some((other) => distance(point, other) < ARC_CROWDING),
          );
          arcCost += crowded.length * COST_ARC_CROWDING;
        }
        for (const t of LABEL_POSITIONS) {
          const label = along(from, control, to, t);
          let cost = arcCost + Math.abs(t - 0.5) * COST_LABEL_DRIFT;
          for (const hub of hubs) {
            if (distance(label, hub) < badgeRadius + pillHalfWidth + PILL_MARGIN) cost += COST_PILL_ON_BADGE;
            const name = { x: hub.x, y: hub.y + nameOffset };
            if (inBox(label, name, nameHalfWidth + pillHalfWidth, nameHalfHeight + pillHalfHeight)) cost += COST_PILL_ON_NAME;
          }
          for (const pill of placedPills) {
            if (inBox(label, pill, pillWidthGap, pillHeightGap)) cost += COST_PILL_ON_PILL;
          }
          for (const placed of placedArcs) {
            const crossesPill = placed.samples.some((point) => inBox(point, label, pillHalfWidth + PILL_MARGIN, pillHalfHeight + PILL_MARGIN));
            if (crossesPill) cost += COST_ARC_THROUGH_PILL;
          }
          if (best === null || cost < best.cost) best = { cost, control, label, samples };
        }
      }
    }

    if (best === null) throw new Error(`No layout candidates for link ${key}`);
    layouts.set(key, { control: best.control, label: best.label });
    placedArcs.push({ samples: best.samples, from, to });
    placedPills.push(best.label);
  }
  return layouts;
}
