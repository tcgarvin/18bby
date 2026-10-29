/**
 * The order of corporation traces across each lane border, chosen for the whole map at once.
 *
 * Every border a lane crosses (between two charted tiles, or at a tile's exit into a planet or
 * open space) carries the corporations serving either side, packed side by side around the lane's
 * centre line. Only their order is chosen, and both tiles read it from the same physical edge,
 * so traces always meet at borders. Orders are chosen to minimize, in turn:
 * 1. crossings: two corporations swapping sides inside a tile;
 * 2. lane changes: how far traces drift sideways inside a tile (where a border also carries a
 *    neighbour's corporation, the others shift over to make room);
 * 3. disorder: pairs out of the game's corporation order, read along each border's canonical
 *    normal, so ties are broken the same way everywhere and a new tile seldom flips old traces.
 *
 * Inside a tile traces run from border to border: through a two-exit tile, and through a
 * junction's trunk (see `junctionTrunk`), which runs where the most of its traces carry on. A junction's branch, and a lane's end at a planet or in
 * open space, can take any order, so they only follow the borders they continue. A junction
 * served by more than `treeMaxCorps` corporations has an interchange disk instead, over spokes
 * that never cross.
 *
 * Borders joined through tiles carrying the same corporations at both ends form a chain whose
 * orders are fixed by any one of them, and the search runs over chains: each tries every order
 * of its corporations in turn, keeping improvements, until none improves.
 */

import type { Axial, DirectionName } from "./api";
import { DIRECTIONS, hexKey, neighbor } from "./hex";
import { junctionTrunk, oppositeOf } from "./lanes";

export interface LaneTile {
  hex: Axial;
  exits: DirectionName[];
  service: string[];
}

export interface LaneOrderOptions {
  /** Junctions served by more corporations than this draw spokes under an interchange disk. */
  treeMaxCorps: number;
  /** Whether lanes run into the hex at this `hexKey` (a planet, or the construction site). */
  isHub: (key: string) => boolean;
}

export interface LaneOrder {
  /** Corporations on each border by `edgeKey`, in order along its canonical normal. */
  orders: Map<string, string[]>;
  /** The trunk and branch of each junction drawn as a tree of traces, by tile `hexKey`. */
  trunks: Map<string, { trunk: [DirectionName, DirectionName]; branch: DirectionName }>;
}

/** A key for the physical edge on `exit`'s side of `hex`, the same from the hex beyond it. */
export function edgeKey(hex: Axial, exit: DirectionName): string {
  return DIRECTIONS.indexOf(exit) < 3 ? `${hexKey(hex)}>${exit}` : `${hexKey(neighbor(hex, exit))}>${oppositeOf(exit)}`;
}

/**
 * Offset of `corp`'s trace on the border on `exit`'s side of `hex`, in trace spacings along the
 * border's canonical normal from the lane's centre line.
 */
export function slotOffset(order: LaneOrder, hex: Axial, exit: DirectionName, corp: string): number {
  const corps = order.orders.get(edgeKey(hex, exit));
  const index = corps?.indexOf(corp) ?? -1;
  if (corps === undefined || index < 0) throw new Error(`${corp} has no slot on the ${exit} border of ${hexKey(hex)}`);
  return index - (corps.length - 1) / 2;
}

/** +1 where the canonical normal of `exit` runs clockwise round the tile, -1 where it runs anticlockwise. */
function normalSign(exit: DirectionName): number {
  return DIRECTIONS.indexOf(exit) < 3 ? 1 : -1;
}

/** Traces running from border `a` to border `b` of a tile: through a two-exit tile, or a junction's trunk. */
interface Link {
  service: string[];
  a: string;
  b: string;
  signA: number;
  signB: number;
}

/** Crossings, then lane drift (in half spacings), then disorder; compared in that order. */
type Cost = [number, number, number];

function addCost(total: Cost, more: Cost): void {
  for (let i = 0; i < 3; i++) total[i] += more[i];
}

function lessThan(a: Cost, b: Cost): boolean {
  for (let i = 0; i < 3; i++) {
    if (a[i] !== b[i]) return a[i] < b[i];
  }
  return false;
}

/** Twice a corporation's slot offset on a border ordered `corps` (an integer). */
function doubledSlot(corps: string[], corp: string): number {
  return 2 * corps.indexOf(corp) - (corps.length - 1);
}

/**
 * Crossings and drift of a link's traces. A trace's side, left of the direction of travel from
 * `a` to `b`, is its slot times the border's normal sign entering at `a`, and minus that leaving
 * at `b`; it drifts by the difference, and two traces cross where their sides swap.
 */
function linkCost(link: Link, orderA: string[], orderB: string[]): Cost {
  const sides = link.service.map((corp) => [doubledSlot(orderA, corp) * link.signA, -doubledSlot(orderB, corp) * link.signB]);
  let crossings = 0;
  let drift = 0;
  for (let i = 0; i < sides.length; i++) {
    drift += Math.abs(sides[i][0] - sides[i][1]);
    for (let j = i + 1; j < sides.length; j++) {
      if ((sides[i][0] - sides[j][0]) * (sides[i][1] - sides[j][1]) < 0) crossings += 1;
    }
  }
  return [crossings, drift, 0];
}

function disorder(corps: string[], rank: Map<string, number>): number {
  let pairs = 0;
  for (let i = 0; i < corps.length; i++) {
    for (let j = i + 1; j < corps.length; j++) {
      if ((rank.get(corps[i]) ?? 0) > (rank.get(corps[j]) ?? 0)) pairs += 1;
    }
  }
  return pairs;
}

function permutations<T>(items: T[]): T[][] {
  if (items.length <= 1) return [items];
  return items.flatMap((item, i) => permutations([...items.slice(0, i), ...items.slice(i + 1)]).map((rest) => [item, ...rest]));
}

/** Union-find over borders, tracking whether each border's order is its root's reversed. */
class Chains {
  private parent = new Map<string, string>();
  private flipped = new Map<string, boolean>();

  add(edge: string): void {
    if (!this.parent.has(edge)) {
      this.parent.set(edge, edge);
      this.flipped.set(edge, false);
    }
  }

  find(edge: string): { root: string; flipped: boolean } {
    let root = edge;
    let flipped = false;
    while (this.parent.get(root) !== root) {
      flipped = flipped !== this.flipped.get(root);
      root = this.parent.get(root) as string;
    }
    return { root, flipped };
  }

  /** Joins two borders whose orders are each other's reverse when `flipped`; false if that contradicts the chain. */
  join(a: string, b: string, flipped: boolean): boolean {
    const ra = this.find(a);
    const rb = this.find(b);
    if (ra.root === rb.root) return (ra.flipped !== rb.flipped) === flipped;
    this.parent.set(rb.root, ra.root);
    this.flipped.set(rb.root, ra.flipped !== rb.flipped !== flipped);
    return true;
  }
}

/** Search passes over the chains; each pass that changes nothing ends it sooner. */
const MAX_PASSES = 12;

/** The order of corporations across every lane border of `tiles` (see the module comment). */
export function solveLaneOrder(tiles: LaneTile[], corpIds: string[], options: LaneOrderOptions): LaneOrder {
  const rank = new Map(corpIds.map((corp, i) => [corp, i] as const));
  const byRank = (a: string, b: string): number => (rank.get(a) ?? 0) - (rank.get(b) ?? 0);
  const sets = new Map<string, Set<string>>();
  for (const tile of tiles) {
    for (const exit of tile.exits) {
      const key = edgeKey(tile.hex, exit);
      const set = sets.get(key) ?? new Set<string>();
      for (const corp of tile.service) set.add(corp);
      sets.set(key, set);
    }
  }
  const corpsOn = (edge: string): string[] => [...(sets.get(edge) ?? [])].sort(byRank);
  const sameCorps = (a: string, b: string): boolean => corpsOn(a).join(" ") === corpsOn(b).join(" ");

  const tilesByKey = new Map(tiles.map((tile) => [hexKey(tile.hex), tile] as const));
  /** How many of `tile`'s corporations carry on through `exit`: into a planet, or along the next tile. */
  const carryOn = (tile: LaneTile, exit: DirectionName): number => {
    const beyond = neighbor(tile.hex, exit);
    if (options.isHub(hexKey(beyond))) return tile.service.length;
    const next = tilesByKey.get(hexKey(beyond));
    if (next === undefined || !next.exits.includes(oppositeOf(exit))) return 0;
    return tile.service.filter((corp) => next.service.includes(corp)).length;
  };

  const trunks: LaneOrder["trunks"] = new Map();
  const links: Link[] = [];
  for (const tile of tiles) {
    let through: [DirectionName, DirectionName] | null = null;
    if (tile.exits.length === 2) through = [tile.exits[0], tile.exits[1]];
    if (tile.exits.length === 3 && tile.service.length <= options.treeMaxCorps) {
      const junction = junctionTrunk(tile.exits, (exit) => carryOn(tile, exit));
      trunks.set(hexKey(tile.hex), junction);
      through = junction.trunk;
    }
    if (through === null) continue;
    const [from, to] = through;
    links.push({
      service: tile.service,
      a: edgeKey(tile.hex, from),
      b: edgeKey(tile.hex, to),
      signA: normalSign(from),
      signB: normalSign(to),
    });
  }

  // Through a link with the same corporations at both ends, parallel traces need the orders
  // equal where the two normals run opposite ways round the tile, and reversed where they agree.
  const chains = new Chains();
  for (const edge of sets.keys()) chains.add(edge);
  for (const link of links) {
    if (sameCorps(link.a, link.b)) chains.join(link.a, link.b, link.signA === link.signB);
  }
  const members = new Map<string, { edge: string; flipped: boolean }[]>();
  for (const edge of [...sets.keys()].sort()) {
    const { root, flipped } = chains.find(edge);
    members.set(root, [...(members.get(root) ?? []), { edge, flipped }]);
  }
  const rootOrders = new Map([...members.keys()].map((root) => [root, corpsOn(root)] as const));
  const orderOf = (edge: string): string[] => {
    const { root, flipped } = chains.find(edge);
    const order = rootOrders.get(root) ?? [];
    return flipped ? [...order].reverse() : order;
  };
  const linksOf = new Map<string, Link[]>();
  for (const link of links) {
    for (const edge of [link.a, link.b]) {
      const root = chains.find(edge).root;
      const list = linksOf.get(root) ?? [];
      if (!list.includes(link)) list.push(link);
      linksOf.set(root, list);
    }
  }
  const chainCost = (root: string): Cost => {
    const total: Cost = [0, 0, 0];
    for (const link of linksOf.get(root) ?? []) addCost(total, linkCost(link, orderOf(link.a), orderOf(link.b)));
    for (const { edge } of members.get(root) ?? []) total[2] += disorder(orderOf(edge), rank);
    return total;
  };

  const roots = [...members.keys()].filter((root) => corpsOn(root).length > 1);
  for (let pass = 0; pass < MAX_PASSES; pass++) {
    let improved = false;
    for (const root of roots) {
      let best = rootOrders.get(root) ?? [];
      let bestCost = chainCost(root);
      for (const order of permutations(corpsOn(root))) {
        rootOrders.set(root, order);
        const cost = chainCost(root);
        if (lessThan(cost, bestCost)) {
          best = order;
          bestCost = cost;
          improved = true;
        }
      }
      rootOrders.set(root, best);
    }
    if (!improved) break;
  }
  return { orders: new Map([...sets.keys()].map((edge) => [edge, orderOf(edge)] as const)), trunks };
}
