import { describe, expect, it } from "vitest";
import type { Axial, DirectionName } from "./api";
import { DIRECTIONS, hexToPixel, neighbor, type Point } from "./hex";
import {
  apothem,
  canonicalNormal,
  oppositeOf,
  portEnd,
  piecePath,
  pointAt,
  sideVector,
  stubPiece,
  tangentAt,
  tileRoute,
  tracePath,
  tracePoint,
  type LanePiece,
} from "./lanes";

const SIZE = 34;
const HEX: Axial = [2, -1];

function close(a: Point, b: Point, digits = 6): void {
  expect(a.x).toBeCloseTo(b.x, digits);
  expect(a.y).toBeCloseTo(b.y, digits);
}

function edgeMid(hex: Axial, exit: DirectionName): Point {
  const c = hexToPixel(hex, SIZE);
  const u = sideVector(exit);
  return { x: c.x + u.x * apothem(SIZE), y: c.y + u.y * apothem(SIZE) };
}

/** Every combination of 1, 2 or 3 distinct exits. */
function exitSets(): DirectionName[][] {
  const sets: DirectionName[][] = [];
  for (let mask = 1; mask < 64; mask++) {
    const exits = DIRECTIONS.filter((_, i) => mask & (1 << i));
    if (exits.length <= 3) sets.push(exits);
  }
  return sets;
}

/** The piece of a route that touches `exit`, and whether the curve ends (rather than starts) there. */
function pieceAt(pieces: LanePiece[], exit: DirectionName): { piece: LanePiece; atEnd: boolean } {
  for (const piece of pieces) {
    if (piece.endPort?.exit === exit) return { piece, atEnd: true };
    if (piece.startPort?.exit === exit) return { piece, atEnd: false };
  }
  throw new Error(`no piece reaches ${exit}`);
}

describe("canonicalNormal", () => {
  it("is shared by opposite sides and runs along the edge", () => {
    for (const d of DIRECTIONS) {
      close(canonicalNormal(d), canonicalNormal(oppositeOf(d)));
      expect(Math.abs(canonicalNormal(d).x * sideVector(d).x + canonicalNormal(d).y * sideVector(d).y)).toBeLessThan(1e-9);
    }
  });
});

describe("tileRoute", () => {
  it("meets every exit at its edge midpoint, perpendicular to the edge", () => {
    for (const exits of exitSets()) {
      const route = tileRoute(HEX, exits, SIZE);
      for (const exit of exits) {
        const { piece, atEnd } = pieceAt(route.pieces, exit);
        const t = atEnd ? 1 : 0;
        close(pointAt(piece.curve, t), edgeMid(HEX, exit));
        const tangent = tangentAt(piece.curve, t);
        const outward = sideVector(exit);
        // Leaving through the exit at the end, entering from it at the start.
        const along = tangent.x * outward.x + tangent.y * outward.y;
        expect(along).toBeCloseTo(atEnd ? 1 : -1, 6);
      }
    }
  });

  it("draws opposite exits straight and bends with radius 1.5 or 0.5 sides", () => {
    expect(tileRoute(HEX, ["E", "W"], SIZE).pieces[0].curve.kind).toBe("line");
    const gentle = tileRoute(HEX, ["E", "SW"], SIZE).pieces[0].curve;
    const sharp = tileRoute(HEX, ["NW", "NE"], SIZE).pieces[0].curve;
    expect(gentle.kind === "arc" && gentle.radius).toBeCloseTo(1.5 * SIZE, 6);
    expect(sharp.kind === "arc" && sharp.radius).toBeCloseTo(0.5 * SIZE, 6);
    // Gentle bends turn 60 degrees, sharp ones 120.
    expect(gentle.kind === "arc" && Math.abs(gentle.sweep)).toBeCloseTo(Math.PI / 3, 6);
    expect(sharp.kind === "arc" && Math.abs(sharp.sweep)).toBeCloseTo((2 * Math.PI) / 3, 6);
  });

  it("emits exact SVG arcs for bends", () => {
    expect(piecePath(tileRoute(HEX, ["E", "SE"], SIZE).pieces[0])).toMatch(/^M[-\d.,]+A17\.00,17\.00 0 0 [01] [-\d.,]+$/);
  });

  it("starts a two-exit route at the requested exit", () => {
    const piece = tileRoute(HEX, ["E", "SW"], SIZE, { startExit: "SW" }).pieces[0];
    expect(piece.startPort?.exit).toBe("SW");
    close(pointAt(piece.curve, 0), edgeMid(HEX, "SW"));
  });

  it("joins three exits at a junction with one straight spoke per exit", () => {
    for (const exits of [["E", "SW", "NW"], ["E", "SE", "W"], ["E", "SE", "SW"]] as DirectionName[][]) {
      const route = tileRoute(HEX, exits, SIZE);
      expect(route.junction).not.toBeNull();
      expect(route.pieces).toHaveLength(3);
      for (const piece of route.pieces) {
        expect(piece.curve.kind).toBe("line");
        close(pointAt(piece.curve, 0), route.center);
      }
    }
    expect(tileRoute(HEX, ["E"], SIZE).junction).toBeNull();
  });

  it("produces finite path data for every exit combination", () => {
    for (const exits of exitSets()) {
      const route = tileRoute(HEX, exits, SIZE);
      for (const piece of route.pieces) {
        for (const offset of [-3.9, 0, 2.6]) {
          const d = piecePath(piece) + tracePath(piece, offset);
          expect(d).not.toMatch(/NaN|Infinity/);
        }
      }
    }
  });

  it("cuts a dangling end short by the requested length", () => {
    const full = tileRoute(HEX, ["E", "NW"], SIZE).pieces[0];
    const cut = tileRoute(HEX, ["E", "NW"], SIZE, { trims: { NW: 7 } }).pieces[0];
    expect(cut.t1).toBeLessThan(1);
    const end = portEnd(cut, "NW")?.at ?? { x: NaN, y: NaN };
    const edge = edgeMid(HEX, "NW");
    // Along a gentle arc the chord is a hair shorter than the arc length cut off.
    expect(Math.hypot(end.x - edge.x, end.y - edge.y)).toBeGreaterThan(6.95);
    expect(Math.hypot(end.x - edge.x, end.y - edge.y)).toBeLessThanOrEqual(7.0001);
    expect(full.t1).toBe(1);
  });
});

describe("traces", () => {
  it("meet at the same point across the border between adjacent tiles", () => {
    const offsets = [-3.9, -1.3, 1.3, 3.9];
    for (const exitsA of exitSets().filter((s) => s.length >= 2)) {
      for (const exit of exitsA) {
        const other = neighbor(HEX, exit);
        const back = oppositeOf(exit);
        for (const exitsB of exitSets().filter((set) => set.length >= 2 && set.includes(back))) {
          const a = pieceAt(tileRoute(HEX, exitsA, SIZE).pieces, exit);
          const b = pieceAt(tileRoute(other, exitsB, SIZE).pieces, back);
          for (const offset of offsets) {
            close(tracePoint(a.piece, offset, a.atEnd ? 1 : 0), tracePoint(b.piece, offset, b.atEnd ? 1 : 0));
          }
        }
      }
    }
  });

  it("continue into a planet's stub without a jump", () => {
    const planet: Axial = neighbor(HEX, "SE");
    const tile = pieceAt(tileRoute(HEX, ["SE", "NW"], SIZE).pieces, "SE");
    const stub = stubPiece(planet, "NW", SIZE);
    for (const offset of [-3.9, 3.9]) {
      close(tracePoint(tile.piece, offset, tile.atEnd ? 1 : 0), tracePoint(stub, offset, 0));
      // The stub keeps that offset all the way in.
      const distance = (t: number): number => {
        const p = tracePoint(stub, offset, t);
        const q = pointAt(stub.curve, t);
        return Math.hypot(p.x - q.x, p.y - q.y);
      };
      expect(distance(0.5)).toBeCloseTo(Math.abs(offset), 6);
    }
  });

  it("change sides mid-tile when the two borders put the slot on different sides", () => {
    const piece = tileRoute(HEX, ["E", "SE"], SIZE).pieces[0];
    const curve = piece.curve;
    if (curve.kind !== "arc") throw new Error("expected an arc");
    const side = (t: number): number => {
      const p = tracePoint(piece, 2.6, t);
      return Math.hypot(p.x - curve.center.x, p.y - curve.center.y) - curve.radius;
    };
    expect(side(0)).toBeCloseTo(-side(1), 6);
    expect(Math.abs(side(0))).toBeCloseTo(2.6, 6);
    // Settled on each side for the first and last fifth of the tile.
    expect(side(0.15)).toBeCloseTo(side(0), 6);
    expect(side(0.85)).toBeCloseTo(side(1), 6);
  });

  it("draw paths that start and end where tracePoint puts them, parallel or not", () => {
    const ends = (d: string): [Point, Point] => {
      const numbers = [...d.matchAll(/-?\d+(?:\.\d+)?/g)].map((m) => Number(m[0]));
      return [
        { x: numbers[0], y: numbers[1] },
        { x: numbers[numbers.length - 2], y: numbers[numbers.length - 1] },
      ];
    };
    for (const exits of exitSets()) {
      const route = tileRoute(HEX, exits, SIZE, { trims: { [exits[0]]: 5 } });
      for (const piece of route.pieces) {
        for (const offset of [-3.9, 1.3]) {
          const [start, end] = ends(tracePath(piece, offset));
          close(start, tracePoint(piece, offset, piece.t0), 2);
          close(end, tracePoint(piece, offset, piece.t1), 2);
        }
      }
    }
  });

  it("run parallel to junction spokes, close enough to the centre for the interchange disk to cover", () => {
    const route = tileRoute(HEX, ["E", "SE", "W"], SIZE);
    for (const piece of route.pieces) {
      for (const offset of [-3.9, 3.9]) {
        const p = tracePoint(piece, offset, 0);
        expect(Math.hypot(p.x - route.center.x, p.y - route.center.y)).toBeCloseTo(3.9, 6);
      }
    }
  });
});
