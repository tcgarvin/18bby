/**
 * Geometry of hyperspace lanes on the map: the route a charted tile draws through its exits, the
 * stubs that run into planets, and the offset traces of the corporations serving them.
 *
 * A tile's exits all connect through the tile (it is a hub, not point-to-point track), so:
 * - two exits on opposite sides are a straight lane;
 * - two exits two sides apart bend gently (a circular arc of radius 1.5 sides), and two adjacent
 *   exits bend sharply (radius 0.5 sides);
 * - three exits (a junction) draw some of these bends between pairs of them, as `laneOrder.ts`
 *   chooses: a fork of two bends out of one exit, like railway track, or more where corporations
 *   fork out of different exits;
 * - one exit is a single spoke from the hex centre.
 * Every route meets the hex border at the edge midpoint, perpendicular to the edge, so lanes flow
 * from tile to tile with no visible joint.
 *
 * Corporation traces run parallel to the route, at an offset measured along `canonicalNormal` at
 * each border, which both tiles sharing that edge agree on, so a corporation's trace leaves one
 * tile exactly where it enters the next. Where its offsets at the two ends of a piece differ it
 * drifts across mid-tile. `laneOrder.ts` chooses the offsets.
 */

import type { Axial, DirectionName } from "./api";
import { DIRECTIONS, edgeMidpoint, hexKey, hexToPixel, type Point } from "./hex";

// ---------- Points ----------

function add(a: Point, b: Point, scale = 1): Point {
  return { x: a.x + b.x * scale, y: a.y + b.y * scale };
}

function sub(a: Point, b: Point): Point {
  return { x: a.x - b.x, y: a.y - b.y };
}

function dot(a: Point, b: Point): number {
  return a.x * b.x + a.y * b.y;
}

function unit(p: Point): Point {
  const length = Math.hypot(p.x, p.y);
  return { x: p.x / length, y: p.y / length };
}

function polar(radians: number): Point {
  return { x: Math.cos(radians), y: Math.sin(radians) };
}

/** The normal to the left of a direction of travel, as seen on screen (y down). */
export function leftNormal(tangent: Point): Point {
  return { x: tangent.y, y: -tangent.x };
}

function fmt(p: Point): string {
  return `${p.x.toFixed(2)},${p.y.toFixed(2)}`;
}

// ---------- Directions ----------

export function oppositeOf(direction: DirectionName): DirectionName {
  return DIRECTIONS[(DIRECTIONS.indexOf(direction) + 3) % 6];
}

/** Unit vector from a hex centre toward the midpoint of its `direction` side. */
export function sideVector(direction: DirectionName): Point {
  return polar((DIRECTIONS.indexOf(direction) * Math.PI) / 3);
}

/**
 * A unit vector along the edge on `direction`'s side that both hexes sharing that edge agree on
 * (opposite directions give the same vector), so trace slots line up across the border.
 */
export function canonicalNormal(direction: DirectionName): Point {
  const index = DIRECTIONS.indexOf(direction);
  const base = sideVector(index < 3 ? direction : oppositeOf(direction));
  return { x: -base.y, y: base.x };
}

/** Centre-to-edge-midpoint distance of a hex with side `size`. */
export function apothem(size: number): number {
  return (Math.sqrt(3) / 2) * size;
}

// ---------- Curves ----------

export interface LineCurve {
  kind: "line";
  from: Point;
  to: Point;
}

/** A circular arc; signed `sweep` in radians, positive clockwise on screen. */
export interface ArcCurve {
  kind: "arc";
  center: Point;
  radius: number;
  start: number;
  sweep: number;
}

export type Curve = LineCurve | ArcCurve;

export function pointAt(curve: Curve, t: number): Point {
  if (curve.kind === "line") return add(curve.from, sub(curve.to, curve.from), t);
  return add(curve.center, polar(curve.start + curve.sweep * t), curve.radius);
}

/** Unit tangent in the direction of travel. */
export function tangentAt(curve: Curve, t: number): Point {
  if (curve.kind === "line") return unit(sub(curve.to, curve.from));
  const radial = polar(curve.start + curve.sweep * t);
  const sign = Math.sign(curve.sweep);
  return { x: -radial.y * sign, y: radial.x * sign };
}

export function curveLength(curve: Curve): number {
  if (curve.kind === "line") return Math.hypot(curve.to.x - curve.from.x, curve.to.y - curve.from.y);
  return Math.abs(curve.sweep) * curve.radius;
}

/** SVG path data for the part of `curve` between t0 and t1. */
export function curvePath(curve: Curve, t0 = 0, t1 = 1): string {
  const start = `M${fmt(pointAt(curve, t0))}`;
  const end = pointAt(curve, t1);
  if (curve.kind === "line") return `${start}L${fmt(end)}`;
  const large = Math.abs(curve.sweep * (t1 - t0)) > Math.PI ? 1 : 0;
  const sweepFlag = curve.sweep > 0 ? 1 : 0;
  const r = curve.radius.toFixed(2);
  return `${start}A${r},${r} 0 ${large} ${sweepFlag} ${fmt(end)}`;
}

/**
 * The curve running parallel to `curve`, `side` units to the left of travel: a shifted line, a
 * concentric arc (never below radius 0).
 */
export function parallelCurve(curve: Curve, side: number): Curve {
  if (curve.kind === "line") {
    const n = leftNormal(tangentAt(curve, 0));
    return { kind: "line", from: add(curve.from, n, side), to: add(curve.to, n, side) };
  }
  // Left of travel points away from the centre on a clockwise (positive sweep) arc.
  return { ...curve, radius: Math.max(0, curve.radius + Math.sign(curve.sweep) * side) };
}

/**
 * Edge-to-edge curve between exits `from` and `to`: a straight line for opposite sides,
 * otherwise the circular arc that meets both edges at a right angle at their midpoints.
 */
export function bendCurve(center: Point, from: DirectionName, to: DirectionName, size: number): Curve {
  const a = apothem(size);
  const ui = sideVector(from);
  const uj = sideVector(to);
  const start = add(center, ui, a);
  const end = add(center, uj, a);
  const steps = (DIRECTIONS.indexOf(to) - DIRECTIONS.indexOf(from) + 6) % 6;
  if (steps === 3) return { kind: "line", from: start, to: end };
  // `theta` is the angle between the two sides' directions. The circle through both midpoints,
  // tangent to the hex's radii there, has its centre on their bisector, outside the hex.
  const theta = (Math.min(steps, 6 - steps) * Math.PI) / 3;
  const radius = a * Math.tan(theta / 2);
  const circle = add(center, add(ui, uj), a / (1 + Math.cos(theta)));
  const startAngle = Math.atan2(start.y - circle.y, start.x - circle.x);
  const endAngle = Math.atan2(end.y - circle.y, end.x - circle.x);
  let sweep = endAngle - startAngle;
  while (sweep > Math.PI) sweep -= 2 * Math.PI;
  while (sweep <= -Math.PI) sweep += 2 * Math.PI;
  return { kind: "arc", center: circle, radius, start: startAngle, sweep };
}

/** Steps round the hex between two sides: 1 for adjacent sides, 2 for two apart, 3 for opposite. */
export function sidesApart(a: DirectionName, b: DirectionName): number {
  const steps = (DIRECTIONS.indexOf(b) - DIRECTIONS.indexOf(a) + 6) % 6;
  return Math.min(steps, 6 - steps);
}

// ---------- Routes ----------

/** Where a lane piece meets a hex border: the side, and the canonical normal that slots are measured along. */
export interface Port {
  exit: DirectionName;
  normal: Point;
}

/**
 * One drawable stroke of a route: a bend from edge to edge (a two-exit tile has one, a junction
 * several), a spoke from a one-exit tile's centre out to its edge, or a planet stub from the
 * planet's edge to its centre.
 */
export interface LanePiece {
  key: string;
  curve: Curve;
  /** The drawn part of the curve; less than [0, 1] where a dangling end cuts the lane short. */
  t0: number;
  t1: number;
  /** The border the curve starts on, or null when it starts at the tile's centre (a spoke). */
  startPort: Port | null;
  /** The border the curve ends on, or null when it ends at a planet's centre (a stub). */
  endPort: Port | null;
}

export interface TileRoute {
  hex: Axial;
  center: Point;
  pieces: LanePiece[];
}

export interface RouteOptions {
  /** Draw bends starting from this exit where they reach it (fresh lanes draw in from their start). */
  startExit?: DirectionName;
  /** The bends a junction draws (see `laneOrder.ts`); by default a fork from its gentlest stem. */
  bends?: [DirectionName, DirectionName][];
  /** Lane length to leave off at these exits: the lane ends early (a dangling end). */
  trims?: Partial<Record<DirectionName, number>>;
}

function port(exit: DirectionName): Port {
  return { exit, normal: canonicalNormal(exit) };
}

/** The drawn parameter range of a curve with `startCut` and `endCut` of its length left off. */
function trimmed(curve: Curve, startCut: number, endCut: number): { t0: number; t1: number } {
  const length = curveLength(curve);
  return { t0: startCut / length, t1: 1 - endCut / length };
}

/** A junction's bends when none are given: a fork out of the exit whose two bends are gentlest. */
function defaultFork(exits: DirectionName[]): [DirectionName, DirectionName][] {
  const forks = exits.map((stem) => exits.filter((exit) => exit !== stem).map((exit): [DirectionName, DirectionName] => [stem, exit]));
  const sharp = (fork: [DirectionName, DirectionName][]): number => fork.filter(([a, b]) => sidesApart(a, b) === 1).length;
  return forks.sort((a, b) => sharp(a) - sharp(b))[0];
}

/** The route a charted tile draws through its exits. */
export function tileRoute(hex: Axial, exits: DirectionName[], size: number, options: RouteOptions = {}): TileRoute {
  const center = hexToPixel(hex, size);
  const key = hexKey(hex);
  const cut = (exit: DirectionName): number => options.trims?.[exit] ?? 0;
  if (exits.length === 1) {
    const [exit] = exits;
    const curve: Curve = { kind: "line", from: center, to: add(center, sideVector(exit), apothem(size)) };
    return { hex, center, pieces: [{ key: `${key}>${exit}`, curve, ...trimmed(curve, 0, cut(exit)), startPort: null, endPort: port(exit) }] };
  }
  const bends = exits.length === 2 ? [[exits[0], exits[1]] as [DirectionName, DirectionName]] : (options.bends ?? defaultFork(exits));
  const pieces = bends.map(([a, b]): LanePiece => {
    const [from, to] = options.startExit === b ? [b, a] : [a, b];
    const curve = bendCurve(center, from, to, size);
    return {
      key: `${key}:${[from, to].sort().join("-")}`,
      curve,
      ...trimmed(curve, cut(from), cut(to)),
      startPort: port(from),
      endPort: port(to),
    };
  });
  return { hex, center, pieces };
}

/** The stub from a planet's edge on `side` to its centre (the badge covers the inner part). */
export function stubPiece(planetHex: Axial, side: DirectionName, size: number): LanePiece {
  const center = hexToPixel(planetHex, size);
  const curve: Curve = { kind: "line", from: add(center, edgeMidpoint(side, size)), to: center };
  return { key: `stub:${hexKey(planetHex)}:${side}`, curve, t0: 0, t1: 1, startPort: port(side), endPort: null };
}

/**
 * Where the drawn part of a piece ends toward `exit` (short of the border when trimmed), with the
 * unit tangent pointing out toward that exit; null when the piece does not reach `exit`.
 */
export function portEnd(piece: LanePiece, exit: DirectionName): { at: Point; tangent: Point } | null {
  if (piece.endPort?.exit === exit) return { at: pointAt(piece.curve, piece.t1), tangent: tangentAt(piece.curve, piece.t1) };
  if (piece.startPort?.exit === exit) {
    const tangent = tangentAt(piece.curve, piece.t0);
    return { at: pointAt(piece.curve, piece.t0), tangent: { x: -tangent.x, y: -tangent.y } };
  }
  return null;
}

export function piecePath(piece: LanePiece): string {
  return curvePath(piece.curve, piece.t0, piece.t1);
}

// ---------- Traces ----------

/** A trace that must change sides does so over the middle 60% of the tile. */
const CROSSOVER: [number, number] = [0.2, 0.8];

function smoothstep5(t: number): number {
  const [low, high] = CROSSOVER;
  const q = Math.min(1, Math.max(0, (t - low) / (high - low)));
  return q * q * q * (q * (q * 6 - 15) + 10);
}

/**
 * Where a trace runs at each end of a piece, as a signed distance left of the route: `start`
 * along the start port's canonical normal, `end` along the end port's. An end without a port (a
 * spoke's centre, a stub's planet) keeps the other end's side.
 */
function traceSides(piece: LanePiece, start: number, end: number): [number, number] {
  const { curve, startPort, endPort } = piece;
  const side = (at: Port, offset: number, t: number): number => offset * dot(at.normal, leftNormal(tangentAt(curve, t)));
  const first = startPort ? side(startPort, start, 0) : null;
  const last = endPort ? side(endPort, end, 1) : null;
  return [first ?? last ?? 0, last ?? first ?? 0];
}

/**
 * Where a trace runs at parameter t, `start` and `end` units along the canonical normals of the
 * piece's start and end borders: parallel to the route, blending smoothly mid-tile from one
 * side to the other where the two differ.
 */
export function tracePoint(piece: LanePiece, start: number, end: number, t: number): Point {
  const [first, last] = traceSides(piece, start, end);
  const h = Math.abs(first - last) < 1e-9 ? 0 : smoothstep5(t);
  return add(pointAt(piece.curve, t), leftNormal(tangentAt(piece.curve, t)), (1 - h) * first + h * last);
}

/** A trace that changes sides is drawn as cubic Hermite segments through this many samples. */
const TRACE_SEGMENTS = 12;

/**
 * SVG path data for a corporation's trace, `start` and `end` units along the canonical normals
 * of the piece's start and end borders (see `tracePoint`).
 */
export function tracePath(piece: LanePiece, start: number, end: number = start): string {
  const { curve, t0, t1 } = piece;
  const [first, last] = traceSides(piece, start, end);
  // A parallel offset is exact: a shifted line or a concentric arc.
  if (Math.abs(first - last) < 1e-9) return curvePath(parallelCurve(curve, first), t0, t1);
  const at = (t: number): Point => tracePoint(piece, start, end, t);
  const eps = 1e-4;
  const velocity = (t: number): Point => {
    const lo = Math.max(0, t - eps);
    const hi = Math.min(1, t + eps);
    const d = sub(at(hi), at(lo));
    return { x: d.x / (hi - lo), y: d.y / (hi - lo) };
  };
  const step = (t1 - t0) / TRACE_SEGMENTS;
  let previous = at(t0);
  let previousVelocity = velocity(t0);
  const parts = [`M${fmt(previous)}`];
  for (let i = 1; i <= TRACE_SEGMENTS; i++) {
    const t = t0 + step * i;
    const point = at(t);
    const v = velocity(t);
    parts.push(`C${fmt(add(previous, previousVelocity, step / 3))} ${fmt(add(point, v, -step / 3))} ${fmt(point)}`);
    previous = point;
    previousVelocity = v;
  }
  return parts.join("");
}
