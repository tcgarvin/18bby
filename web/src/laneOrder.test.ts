import { describe, expect, it } from "vitest";
import type { Axial, DirectionName } from "./api";
import { DIRECTIONS, hexKey, neighbor } from "./hex";
import { edgeKey, slotOffset, solveLaneOrder, type LaneOrder, type LaneTile } from "./laneOrder";
import { leftNormal, oppositeOf, pointAt, tangentAt, tileRoute, tracePoint, trunkPiece, type LanePiece } from "./lanes";

const SIZE = 34;
const CORPS = ["A", "B", "C", "D"];
const OPTIONS = { treeMaxCorps: 2, isHub: () => false };

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

  it("runs two corporations parallel along a junction's trunk, wherever the lanes beyond lead", () => {
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
      expect(order.trunks.get(hexKey([0, 0]))).toEqual({ trunk: ["E", "W"], branch });
      const piece = trunkPiece(junction.hex, "E", "W", SIZE, 5);
      const ends = sides(order, junction, piece, "E", "W");
      expect(crossings(ends)).toBe(0);
      for (const [start, end] of ends) expect(start).toBeCloseTo(end, 6);
      for (const tile of tiles.slice(1)) {
        const [from, to] = tile.exits;
        const bend = tileRoute(tile.hex, tile.exits, SIZE, { startExit: from }).pieces[0];
        expect(crossings(sides(order, tile, bend, from, to))).toBe(0);
      }
    }
  });

  it("runs a Y junction's trunk where its traces carry on, into tiles or planets", () => {
    // Exits E, SW and NW are all two sides apart. Both corporations carry on to the east and
    // into a planet to the north-west; only one carries on to the south-west.
    const junction: LaneTile = { hex: [0, 0], exits: ["E", "SW", "NW"], service: ["A", "B"] };
    const tiles: LaneTile[] = [
      junction,
      { hex: neighbor([0, 0], "E"), exits: ["W", "E"], service: ["A", "B"] },
      { hex: neighbor([0, 0], "SW"), exits: ["NE", "SW"], service: ["A"] },
    ];
    const planet = hexKey(neighbor([0, 0], "NW"));
    const order = solveLaneOrder(tiles, CORPS, { ...OPTIONS, isHub: (key) => key === planet });
    expect(order.trunks.get(hexKey([0, 0]))).toEqual({ trunk: ["E", "NW"], branch: "SW" });
  });

  it("draws a junction busier than treeMaxCorps as spokes, with no trunk", () => {
    const tiles: LaneTile[] = [{ hex: [0, 0], exits: ["W", "E", "SE"], service: ["A", "B", "C"] }];
    expect(solveLaneOrder(tiles, CORPS, OPTIONS).trunks.size).toBe(0);
    expect(solveLaneOrder(tiles, CORPS, { ...OPTIONS, treeMaxCorps: 3 }).trunks.size).toBe(1);
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
