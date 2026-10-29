/**
 * Geometry of hyperspace lanes on the map: the route a charted tile draws through its exits, the
 * stubs that run into planets, and the offset traces of the corporations serving them.
 *
 * A tile's exits all connect through the tile (it is a hub, not point-to-point track), so:
 * - two exits on opposite sides are a straight lane;
 * - two exits two sides apart bend gently (a circular arc of radius 1.5 sides), and two adjacent
 *   exits bend sharply (radius 0.5 sides);
 * - three exits are straight spokes from the hex centre;
 * - one exit is a single spoke.
 * Every route meets the hex border at the edge midpoint, perpendicular to the edge, so lanes flow
 * from tile to tile with no visible joint.
 *
 * Corporation traces run parallel to the route, at an offset measured along `canonicalNormal` at
 * each border, which both tiles sharing that edge agree on, so a corporation's trace leaves one
 * tile exactly where it enters the next. Where its offsets at the two ends of a piece differ it
 * drifts across mid-tile. Through a junction a trace runs along a trunk (two of the spokes, with
 * the corner rounded) and branches straight down the third spoke onto it. `laneOrder.ts` chooses
 * the offsets.
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

/** Lines and arcs end to end, each starting where the last ends and in the same direction. */
export interface ChainCurve {
  kind: "chain";
  parts: (LineCurve | ArcCurve)[];
}

export type Curve = LineCurve | ArcCurve | ChainCurve;

/** The part of a chain at parameter t of the whole, and t within that part (by length). */
function locate(chain: ChainCurve, t: number): { part: LineCurve | ArcCurve; t: number } {
  const lengths = chain.parts.map(curveLength);
  let along = t * lengths.reduce((sum, length) => sum + length, 0);
  for (let i = 0; i < chain.parts.length - 1; i++) {
    if (along <= lengths[i]) return { part: chain.parts[i], t: along / lengths[i] };
    along -= lengths[i];
  }
  const last = chain.parts.length - 1;
  return { part: chain.parts[last], t: along / lengths[last] };
}

export function pointAt(curve: Curve, t: number): Point {
  if (curve.kind === "chain") {
    const at = locate(curve, t);
    return pointAt(at.part, at.t);
  }
  if (curve.kind === "line") return add(curve.from, sub(curve.to, curve.from), t);
  return add(curve.center, polar(curve.start + curve.sweep * t), curve.radius);
}

/** Unit tangent in the direction of travel. */
export function tangentAt(curve: Curve, t: number): Point {
  if (curve.kind === "chain") {
    const at = locate(curve, t);
    return tangentAt(at.part, at.t);
  }
  if (curve.kind === "line") return unit(sub(curve.to, curve.from));
  const radial = polar(curve.start + curve.sweep * t);
  const sign = Math.sign(curve.sweep);
  return { x: -radial.y * sign, y: radial.x * sign };
}

export function curveLength(curve: Curve): number {
  if (curve.kind === "chain") return curve.parts.reduce((sum, part) => sum + curveLength(part), 0);
  if (curve.kind === "line") return Math.hypot(curve.to.x - curve.from.x, curve.to.y - curve.from.y);
  return Math.abs(curve.sweep) * curve.radius;
}

/** SVG path commands (after the initial move) for a line or arc between t0 and t1. */
function segmentPath(curve: LineCurve | ArcCurve, t0: number, t1: number): string {
  const end = pointAt(curve, t1);
  if (curve.kind === "line") return `L${fmt(end)}`;
  const large = Math.abs(curve.sweep * (t1 - t0)) > Math.PI ? 1 : 0;
  const sweepFlag = curve.sweep > 0 ? 1 : 0;
  const r = curve.radius.toFixed(2);
  return `A${r},${r} 0 ${large} ${sweepFlag} ${fmt(end)}`;
}

/** SVG path data for the part of `curve` between t0 and t1. */
export function curvePath(curve: Curve, t0 = 0, t1 = 1): string {
  const start = `M${fmt(pointAt(curve, t0))}`;
  if (curve.kind !== "chain") return start + segmentPath(curve, t0, t1);
  const total = curveLength(curve);
  const [from, to] = [t0 * total, t1 * total];
  const commands = [start];
  let reached = 0;
  for (const part of curve.parts) {
    const length = curveLength(part);
    const low = Math.max(from, reached);
    const high = Math.min(to, reached + length);
    if (high - low > 1e-9) commands.push(segmentPath(part, (low - reached) / length, (high - reached) / length));
    reached += length;
  }
  return commands.join("");
}

/**
 * The curve running parallel to `curve`, `side` units to the left of travel: a shifted line, a
 * concentric arc (never below radius 0), or a chain of those.
 */
export function parallelCurve(curve: Curve, side: number): Curve {
  if (curve.kind === "chain") return { kind: "chain", parts: curve.parts.map((part) => parallelCurve(part, side) as LineCurve | ArcCurve) };
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
function sidesApart(a: DirectionName, b: DirectionName): number {
  const steps = (DIRECTIONS.indexOf(b) - DIRECTIONS.indexOf(a) + 6) % 6;
  return Math.min(steps, 6 - steps);
}

/**
 * Edge-to-edge curve between exits `from` and `to` that follows their spokes: in along one, out
 * along the other, the corner at the centre rounded with radius `radius`. Opposite exits are a
 * straight line.
 */
export function spokeCurve(center: Point, from: DirectionName, to: DirectionName, size: number, radius: number): Curve {
  const a = apothem(size);
  const ui = sideVector(from);
  const uj = sideVector(to);
  const start = add(center, ui, a);
  const end = add(center, uj, a);
  const steps = sidesApart(from, to);
  if (steps === 3) return { kind: "line", from: start, to: end };
  // The circle of `radius` tangent to both spokes has its centre on their bisector and touches
  // each spoke `reach` from the hex centre.
  const theta = (steps * Math.PI) / 3;
  const reach = radius / Math.tan(theta / 2);
  const enter = add(center, ui, reach);
  const leave = add(center, uj, reach);
  const circle = add(center, unit(add(ui, uj)), radius / Math.sin(theta / 2));
  const startAngle = Math.atan2(enter.y - circle.y, enter.x - circle.x);
  const endAngle = Math.atan2(leave.y - circle.y, leave.x - circle.x);
  let sweep = endAngle - startAngle;
  while (sweep > Math.PI) sweep -= 2 * Math.PI;
  while (sweep <= -Math.PI) sweep += 2 * Math.PI;
  return {
    kind: "chain",
    parts: [
      { kind: "line", from: start, to: enter },
      { kind: "arc", center: circle, radius, start: startAngle, sweep },
      { kind: "line", from: leave, to: end },
    ],
  };
}

// ---------- Routes ----------

/** Where a lane piece meets a hex border: the side, and the canonical normal that slots are measured along. */
export interface Port {
  exit: DirectionName;
  normal: Point;
}

/**
 * One drawable stroke of a route. A two-exit tile is one piece from edge to edge; a junction is
 * one spoke per exit from the centre outward; a planet stub runs from the planet's edge to its centre.
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
  /** Centre of the interchange where three or more spokes meet, or null. */
  junction: Point | null;
}

export interface RouteOptions {
  /** Draw a two-exit route starting from this exit (fresh lanes draw in from their start). */
  startExit?: DirectionName;
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

/** The route a charted tile draws through its exits. */
export function tileRoute(hex: Axial, exits: DirectionName[], size: number, options: RouteOptions = {}): TileRoute {
  const center = hexToPixel(hex, size);
  const key = hexKey(hex);
  const cut = (exit: DirectionName): number => options.trims?.[exit] ?? 0;
  if (exits.length === 2) {
    const [from, to] = options.startExit === exits[1] ? [exits[1], exits[0]] : [exits[0], exits[1]];
    const curve = bendCurve(center, from, to, size);
    const piece: LanePiece = {
      key: `${key}:${[from, to].sort().join("-")}`,
      curve,
      ...trimmed(curve, cut(from), cut(to)),
      startPort: port(from),
      endPort: port(to),
    };
    return { hex, center, junction: null, pieces: [piece] };
  }
  const pieces = exits.map((exit): LanePiece => {
    const curve: Curve = { kind: "line", from: center, to: add(center, sideVector(exit), apothem(size)) };
    return { key: `${key}>${exit}`, curve, ...trimmed(curve, 0, cut(exit)), startPort: null, endPort: port(exit) };
  });
  return { hex, center, junction: exits.length > 2 ? center : null, pieces };
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

// ---------- Junction trunks ----------

/**
 * How a junction's traces run: straight through two of its exits (the trunk), widest apart
 * first, with the third (the branch) joining from the side. Among equally wide pairs the one
 * `preference` scores highest wins, then the first in `DIRECTIONS` order.
 */
export function junctionTrunk(
  exits: DirectionName[],
  preference: (exit: DirectionName) => number = () => 0,
): { trunk: [DirectionName, DirectionName]; branch: DirectionName } {
  if (exits.length !== 3) throw new Error(`A junction has three exits, not ${exits.length}`);
  const sorted = [...exits].sort((a, b) => DIRECTIONS.indexOf(a) - DIRECTIONS.indexOf(b));
  const pairs: [DirectionName, DirectionName, DirectionName][] = [
    [sorted[0], sorted[1], sorted[2]],
    [sorted[0], sorted[2], sorted[1]],
    [sorted[1], sorted[2], sorted[0]],
  ];
  const score = ([a, b]: [DirectionName, DirectionName, DirectionName]): [number, number] => [sidesApart(a, b), preference(a) + preference(b)];
  let best = pairs[0];
  for (const pair of pairs.slice(1)) {
    const [apart, preferred] = score(pair);
    const [bestApart, bestPreferred] = score(best);
    if (apart > bestApart || (apart === bestApart && preferred > bestPreferred)) best = pair;
  }
  return { trunk: [best[0], best[1]], branch: best[2] };
}

/**
 * The trunk a junction's traces follow from exit `from` to exit `to`: along the spokes, the
 * corner rounded with `radius`, cut short like the spokes at trimmed exits.
 */
export function trunkPiece(
  hex: Axial,
  from: DirectionName,
  to: DirectionName,
  size: number,
  radius: number,
  trims: Partial<Record<DirectionName, number>> = {},
): LanePiece {
  const curve = spokeCurve(hexToPixel(hex, size), from, to, size, radius);
  return {
    key: `${hexKey(hex)}~${[from, to].sort().join("-")}`,
    curve,
    ...trimmed(curve, trims[from] ?? 0, trims[to] ?? 0),
    startPort: port(from),
    endPort: port(to),
  };
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
  // A parallel offset is exact: a shifted line, a concentric arc, or a chain of them.
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

/** The trunk trace is searched for the branch's meeting point in this many straight steps. */
const BRANCH_SEARCH_STEPS = 96;

/**
 * A junction trace's branch: straight along the `branch` exit's spoke, `offset` units along that
 * border's canonical normal, from where it meets the same corporation's trunk trace (`trunk`
 * with `trunkStart` and `trunkEnd`, as for `tracePath`) out to the border, or to `cut` short of
 * it. It joins the trunk round a corner of radius `joinRadius`, turning toward the trunk's
 * nearer direction, and is drawn outward so a new branch grows from the trunk. `meet` is where
 * the spoke line crosses the trunk trace; `border` where the branch ends.
 */
export function branchTrace(
  trunk: LanePiece,
  trunkStart: number,
  trunkEnd: number,
  hex: Axial,
  branch: DirectionName,
  offset: number,
  size: number,
  joinRadius: number,
  cut = 0,
): { path: string; meet: Point; border: Point } {
  const center = hexToPixel(hex, size);
  const outward = sideVector(branch);
  const inward = { x: -outward.x, y: -outward.y };
  const edge = add(add(center, outward, apothem(size)), canonicalNormal(branch), offset);
  // The nearest crossing of the inward ray with the trunk trace, as a distance from the border,
  // and the trunk's direction there.
  let nearest = Infinity;
  let trunkDirection: Point = inward;
  let previous = tracePoint(trunk, trunkStart, trunkEnd, 0);
  for (let i = 1; i <= BRANCH_SEARCH_STEPS; i++) {
    const point = tracePoint(trunk, trunkStart, trunkEnd, i / BRANCH_SEARCH_STEPS);
    const along = sub(point, previous);
    const denominator = inward.x * along.y - inward.y * along.x;
    if (Math.abs(denominator) > 1e-12) {
      const gap = sub(previous, edge);
      const distance = (gap.x * along.y - gap.y * along.x) / denominator;
      const fraction = (gap.x * inward.y - gap.y * inward.x) / denominator;
      if (distance >= 0 && fraction >= 0 && fraction <= 1 && distance < nearest) {
        nearest = distance;
        trunkDirection = unit(along);
      }
    }
    previous = point;
  }
  if (!Number.isFinite(nearest)) throw new Error(`Branch ${branch} of ${hexKey(hex)} never meets its trunk`);
  const meet = add(edge, inward, nearest);
  const border = add(edge, inward, cut);
  // Turn onto the trunk the way that bends least: the corner is then at most a right angle.
  const onward = dot(trunkDirection, inward) >= 0 ? trunkDirection : { x: -trunkDirection.x, y: -trunkDirection.y };
  const turn = Math.acos(Math.min(1, Math.max(-1, dot(inward, onward))));
  const reach = joinRadius * Math.tan(turn / 2);
  if (turn < 1e-3 || reach >= nearest - cut) return { path: `M${fmt(meet)}L${fmt(border)}`, meet, border };
  const onTrunk = add(meet, onward, reach);
  const onBranch = add(meet, inward, -reach);
  // Drawn outward, from the trunk back up the branch, so the arc turns against the inward turn.
  const clockwiseInward = inward.x * onward.y - inward.y * onward.x > 0;
  const r = joinRadius.toFixed(2);
  return { path: `M${fmt(onTrunk)}A${r},${r} 0 0 ${clockwiseInward ? 0 : 1} ${fmt(onBranch)}L${fmt(border)}`, meet, border };
}
