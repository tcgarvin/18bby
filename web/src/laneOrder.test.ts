import { describe, expect, it } from "vitest";
import type { Axial, DirectionName } from "./api";
import { DIRECTIONS, hexKey, neighbor } from "./hex";
import { edgeKey, slotOffset, solveLaneOrder, type LaneOrder, type LaneTile } from "./laneOrder";
import type { Point } from "./hex";
import { leftNormal, oppositeOf, pointAt, tangentAt, tileRoute, tracePoint, type LanePiece } from "./lanes";

const SIZE = 34;
const CORPS = ["A", "B", "C", "D"];
const OPTIONS = { isHub: () => false };
const SPACING = 2.6;

/** Tiles along a winding path from `start`, each with exits back and onward (the ends face open space). */
function path(start: Axial, moves: DirectionName[], service: string[]): LaneTile[] {
  const tiles: LaneTile[] = [];
  let hex = start;
  let back: DirectionName | null = null;
  for (const move of moves) {
    tiles.push({ hex, exits: back === null ? [move] : [back, move], service });
    back = oppositeOf(move);
    hex = neighbor(hex, move);
  }
  return tiles.filter((tile) => tile.exits.length === 2);
}

/** Signed distance of a trace left of its route at parameter t. */
function side(piece: LanePiece, start: number, end: number, t: number): number {
  const p = tracePoint(piece, start, end, t);
  const q = pointAt(piece.curve, t);
  const n = leftNormal(tangentAt(piece.curve, t));
  return (p.x - q.x) * n.x + (p.y - q.y) * n.y;
}

/** Each corporation's sides at the two ends of a piece running from border `from` to border `to`. */
function sides(order: LaneOrder, tile: LaneTile, piece: LanePiece, from: DirectionName, to: DirectionName): number[][] {
  return tile.service.map((corp) => {
    const [start, end] = [slotOffset(order, tile.hex, from, corp), slotOffset(order, tile.hex, to, corp)];
    return [side(piece, start, end, 0), side(piece, start, end, 1)];
  });
}

/** Each corporation's drawn traces on a tile, as polylines, following the bends `order` gives it. */
function drawnTraces(order: LaneOrder, tile: LaneTile): { corp: string; points: Point[] }[] {
  const lanes = order.tiles.get(hexKey(tile.hex));
  if (lanes === undefined) throw new Error(`No lanes for ${hexKey(tile.hex)}`);
  const pieces = tileRoute(tile.hex, tile.exits, SIZE, { bends: lanes.bends }).pieces;
  return [...lanes.traces].flatMap(([corp, trace]) =>
    trace.bends.map(([a, b]) => {
      const piece = pieces.find((p) => [a, b].includes(p.startPort?.exit as DirectionName) && [a, b].includes(p.endPort?.exit as DirectionName));
      if (piece === undefined) throw new Error(`No ${a}-${b} bend on ${hexKey(tile.hex)}`);
      const [from, to] = [piece.startPort?.exit, piece.endPort?.exit] as DirectionName[];
      const [start, end] = [slotOffset(order, tile.hex, from, corp) * SPACING, slotOffset(order, tile.hex, to, corp) * SPACING];
      return { corp, points: [...Array(201).keys()].map((i) => tracePoint(piece, start, end, i / 200)) };
    }),
  );
}

function segmentsCross(p: Point, q: Point, r: Point, s: Point): boolean {
  const cross = (o: Point, a: Point, b: Point): number => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  return cross(p, q, r) * cross(p, q, s) < 0 && cross(r, s, p) * cross(r, s, q) < 0;
}

/** How many times traces of different corporations cross on a tile, as drawn. */
function drawnCrossings(order: LaneOrder, tile: LaneTile): number {
  const traces = drawnTraces(order, tile);
  let count = 0;
  for (let i = 0; i < traces.length; i++) {
    for (let j = i + 1; j < traces.length; j++) {
      if (traces[i].corp === traces[j].corp) continue;
      const [a, b] = [traces[i].points, traces[j].points];
      for (let m = 1; m < a.length; m++) {
        for (let n = 1; n < b.length; n++) if (segmentsCross(a[m - 1], a[m], b[n - 1], b[n])) count += 1;
      }
    }
  }
  return count;
}

function crossings(ends: number[][]): number {
  let count = 0;
  for (let i = 0; i < ends.length; i++) {
    for (let j = i + 1; j < ends.length; j++) {
      if ((ends[i][0] - ends[j][0]) * (ends[i][1] - ends[j][1]) < 0) count += 1;
    }
  }
  return count;
}

/** Gentle and sharp bends both ways round, many with both normals running the same way round the tile. */
const WINDING: DirectionName[] = ["E", "NE", "E", "SE", "E", "NE", "NW", "W", "NW", "NE", "E", "E", "SE", "SW", "SE", "E", "NE"];

describe("solveLaneOrder", () => {
  it("is tested along a path that never revisits a hex and turns every which way", () => {
    const tiles = path([0, 0], WINDING, ["A"]);
    expect(new Set(tiles.map((tile) => hexKey(tile.hex))).size).toBe(tiles.length);
    const sameWayRound = tiles.filter(({ exits: [a, b] }) => ["E", "SE", "SW"].includes(a) === ["E", "SE", "SW"].includes(b));
    expect(sameWayRound.length).toBeGreaterThanOrEqual(4);
  });

  it("centres a lone corporation on every border", () => {
    const tiles = path([0, 0], WINDING, ["B"]);
    const order = solveLaneOrder(tiles, CORPS, OPTIONS);
    for (const tile of tiles) {
      for (const exit of tile.exits) expect(slotOffset(order, tile.hex, exit, "B")).toBe(0);
    }
  });

  it("keeps corporations sharing a winding lane parallel through every bend", () => {
    const tiles = path([0, 0], WINDING, ["A", "C", "D"]);
    const order = solveLaneOrder(tiles, CORPS, OPTIONS);
    for (const tile of tiles) {
      const [from, to] = tile.exits;
      const piece = tileRoute(tile.hex, tile.exits, SIZE, { startExit: from }).pieces[0];
      const ends = sides(order, tile, piece, from, to);
      expect(crossings(ends)).toBe(0);
      for (const [start, end] of ends) expect(start).toBeCloseTo(end, 6);
      // Packed around the centre line, a spacing apart.
      expect(ends.map(([start]) => start).sort((a, b) => a - b)).toEqual([-1, 0, 1].map((n) => expect.closeTo(n, 6)));
    }
  });

  it("keeps corporations parallel all the way round a ring of lanes", () => {
    const ring: LaneTile[] = DIRECTIONS.map((direction, i) => ({
      hex: neighbor([0, 0], direction),
      exits: [DIRECTIONS[(i + 4) % 6], DIRECTIONS[(i + 2) % 6]],
      service: ["A", "B"],
    }));
    const order = solveLaneOrder(ring, CORPS, OPTIONS);
    for (const tile of ring) {
      const [from, to] = tile.exits;
      const piece = tileRoute(tile.hex, tile.exits, SIZE, { startExit: from }).pieces[0];
      expect(crossings(sides(order, tile, piece, from, to))).toBe(0);
    }
  });

  it("breaks ties by the corporation order, read along the canonical normal", () => {
    const tiles = path([0, 0], ["E", "E", "E"], ["C", "A"]);
    const order = solveLaneOrder(tiles, CORPS, OPTIONS);
    expect(order.orders.get(edgeKey(tiles[0].hex, "E"))).toEqual(["A", "C"]);
  });

  it("gives a border shared by two tiles every corporation on either side, centred", () => {
    const tiles: LaneTile[] = [
      { hex: [0, 0], exits: ["W", "E"], service: ["A", "B"] },
      { hex: [1, 0], exits: ["W", "E"], service: ["B"] },
      { hex: [2, 0], exits: ["W", "E"], service: ["B"] },
    ];
    const order = solveLaneOrder(tiles, CORPS, OPTIONS);
    expect(order.orders.get(edgeKey([0, 0], "E"))).toEqual(["A", "B"]);
    expect(order.orders.get(edgeKey([1, 0], "W"))).toEqual(["A", "B"]);
    expect(slotOffset(order, [1, 0], "E", "B")).toBe(0);
    expect(slotOffset(order, [0, 0], "W", "A")).toBe(-0.5);
  });

  it("forks two corporations through a junction with the one crossing they need, wherever the lanes beyond lead", () => {
    for (const branch of ["SE", "NW", "NE", "SW"] as DirectionName[]) {
      const junction: LaneTile = { hex: [0, 0], exits: ["W", "E", branch], service: ["A", "B"] };
      // Bends beyond each arm, so the arms' orders are not free.
      const tiles: LaneTile[] = [
        junction,
        { hex: neighbor([0, 0], "E"), exits: ["W", "SE"], service: ["A", "B"] },
        { hex: neighbor([0, 0], "W"), exits: ["E", "NE"], service: ["A", "B"] },
        { hex: neighbor([0, 0], branch), exits: [oppositeOf(branch), branch], service: ["A", "B"] },
      ];
      const order = solveLaneOrder(tiles, CORPS, OPTIONS);
      for (const corp of ["A", "B"]) expect(order.tiles.get(hexKey([0, 0]))?.traces.get(corp)?.bends).toHaveLength(2);
      expect(drawnCrossings(order, junction)).toBe(1);
      for (const tile of tiles.slice(1)) expect(drawnCrossings(order, tile)).toBe(0);
    }
  });

  it("orders a fork's ends so two corporations cross once in it, not twice", () => {
    // Into a planet to the west, on to the north-east, and a dead end to the south-west: the
    // west border's order is free, and must suit the fork.
    const junction: LaneTile = { hex: [0, 0], exits: ["W", "NE", "SW"], service: ["A", "B"] };
    const tiles: LaneTile[] = [junction, { hex: neighbor([0, 0], "NE"), exits: ["SW", "NE"], service: ["A", "B"] }];
    for (const corps of [CORPS, [...CORPS].reverse()]) {
      const planet = hexKey(neighbor([0, 0], "W"));
      const order = solveLaneOrder(tiles, corps, { isHub: (key) => key === planet });
      expect(drawnCrossings(order, junction)).toBe(1);
    }
  });

  it("draws no spur into a tile the corporation does not serve", () => {
    const junction: LaneTile = { hex: [0, 0], exits: ["W", "E", "SE"], service: ["A", "B"] };
    const tiles: LaneTile[] = [
      junction,
      { hex: neighbor([0, 0], "E"), exits: ["W", "E"], service: ["A", "B"] },
      { hex: neighbor([0, 0], "SE"), exits: ["NW", "SE"], service: ["B"] },
    ];
    const order = solveLaneOrder(tiles, CORPS, OPTIONS);
    const lanes = order.tiles.get(hexKey([0, 0]));
    expect(lanes?.traces.get("A")).toEqual({ exits: ["W", "E"], bends: [["W", "E"]] });
    expect(lanes?.traces.get("B")?.exits).toEqual(["W", "E", "SE"]);
    expect(order.orders.get(edgeKey([0, 0], "SE"))).toEqual(["B"]);
    // With A on the far side from the spur, nothing crosses.
    expect(drawnCrossings(order, junction)).toBe(0);
  });

  it("changes the order on two of a junction's borders at once to keep a spur clear", () => {
    // B forks on to the east; A turns north-east only. B must be on the outside of the turn on
    // both the west and north-east borders, which no change to one border alone reaches.
    for (const corps of [CORPS, [...CORPS].reverse()]) {
      const junction: LaneTile = { hex: [0, 0], exits: ["W", "E", "NE"], service: ["A", "B"] };
      const tiles: LaneTile[] = [
        junction,
        { hex: neighbor([0, 0], "W"), exits: ["E", "W"], service: ["A", "B"] },
        { hex: neighbor([0, 0], "E"), exits: ["W", "E"], service: ["B"] },
        { hex: neighbor([0, 0], "NE"), exits: ["SW", "NE"], service: ["A", "B"] },
      ];
      expect(drawnCrossings(solveLaneOrder(tiles, corps, OPTIONS), junction)).toBe(0);
    }
  });

  it("still runs a corporation across a junction it carries on from through only one exit", () => {
    const junction: LaneTile = { hex: [0, 0], exits: ["W", "E", "SE"], service: ["A", "B"] };
    const tiles: LaneTile[] = [
      junction,
      { hex: neighbor([0, 0], "W"), exits: ["E", "W"], service: ["B"] },
      { hex: neighbor([0, 0], "E"), exits: ["W", "E"], service: ["A", "B"] },
      { hex: neighbor([0, 0], "SE"), exits: ["NW", "SE"], service: ["B"] },
    ];
    const trace = solveLaneOrder(tiles, CORPS, OPTIONS).tiles.get(hexKey([0, 0]))?.traces.get("A");
    // From E, straight on to W is gentler than the turn to SE.
    expect(trace).toEqual({ exits: ["W", "E"], bends: [["W", "E"]] });
  });

  it("forks three corporations through a junction with only the three crossings they need", () => {
    const junction: LaneTile = { hex: [0, 0], exits: ["W", "E", "SE"], service: ["A", "B", "C"] };
    const order = solveLaneOrder([junction], CORPS, OPTIONS);
    expect(drawnCrossings(order, junction)).toBe(3);
  });

  it("gives each corporation its own bend where they carry on different ways, crossing nothing", () => {
    const junction: LaneTile = { hex: [0, 0], exits: ["W", "E", "SE"], service: ["A", "B", "C"] };
    const tiles: LaneTile[] = [
      junction,
      { hex: neighbor([0, 0], "W"), exits: ["E", "W"], service: ["A", "C"] },
      { hex: neighbor([0, 0], "E"), exits: ["W", "E"], service: ["A", "B"] },
      { hex: neighbor([0, 0], "SE"), exits: ["NW", "SE"], service: ["B", "C"] },
    ];
    const order = solveLaneOrder(tiles, CORPS, OPTIONS);
    const lanes = order.tiles.get(hexKey([0, 0]));
    expect(lanes?.bends.map((bend) => [...bend].sort().join("-")).sort()).toEqual(["E-SE", "E-W", "SE-W"]);
    expect(lanes?.traces.get("A")?.bends).toEqual([["W", "E"]]);
    expect(drawnCrossings(order, junction)).toBe(0);
  });

  it("draws the lane to an exit none of its corporations reaches", () => {
    const junction: LaneTile = { hex: [0, 0], exits: ["W", "E", "SE"], service: ["A"] };
    const tiles: LaneTile[] = [junction, { hex: neighbor([0, 0], "SE"), exits: ["NW", "SE"], service: ["B"] }];
    const lanes = solveLaneOrder(tiles, CORPS, OPTIONS).tiles.get(hexKey([0, 0]));
    expect(lanes?.traces.get("A")?.bends).toEqual([["W", "E"]]);
    expect(lanes?.bends.map((bend) => [...bend].sort().join("-")).sort()).toEqual(["E-W", "SE-W"]);
  });

  it("names each physical edge the same from both sides", () => {
    for (const exit of ["E", "SE", "SW", "W", "NW", "NE"] as DirectionName[]) {
      expect(edgeKey([2, -1], exit)).toBe(edgeKey(neighbor([2, -1], exit), oppositeOf(exit)));
    }
  });

  it("refuses a slot for a corporation not on the border", () => {
    const order = solveLaneOrder(path([0, 0], ["E", "E"], ["A"]), CORPS, OPTIONS);
    expect(() => slotOffset(order, [1, 0], "E", "B")).toThrow(/has no slot/);
  });
});
