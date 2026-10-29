/**
 * How corporation traces run through the lane network, chosen for the whole map at once.
 *
 * On each tile a corporation's trace runs only to the exits where it carries on: into a planet,
 * to the open end of a lane, or into the next tile when it serves that one too (on a junction it
 * reaches at least two exits, so it still crosses the tile). Through two exits that is one bend,
 * the tile's ordinary curve; through three it is a fork, two bends out of one exit (its stem),
 * like railway track. A tile's lane is every bend its corporations follow, plus a bend to any exit
 * none of them reaches.
 *
 * Every border carries the corporations reaching it from either side, packed side by side around
 * the lane's centre line. The solver chooses their order on each border, which both tiles read
 * from the same physical edge, and each fork's stem, to minimize, in turn:
 * 1. crossings: two traces cross inside a tile exactly where their ends alternate round the
 *    tile's edge, so these are counted within each tile, for bends and forks alike;
 * 2. lane changes: how far traces drift sideways along each bend (where a border also carries a
 *    neighbour's corporation, the others shift over to make room);
 * 3. sharp bends: bends between adjacent exits, which forks avoid where they can;
 * 4. disorder: pairs out of the game's corporation order, read along each border's canonical
 *    normal, so ties are broken the same way everywhere and a new tile seldom flips old traces.
 *
 * Borders joined through two-exit tiles carrying the same corporations at both ends form a chain
 * whose orders are fixed by any one of them. The search tries orders of each chain's corporations
 * and stems of each junction's forks in turn, and the orders of two chains meeting at a junction
 * together, keeping improvements, until a pass improves nothing (it tries every order and every
 * combination of stems where there are few, otherwise single changes).
 */

import type { Axial, DirectionName } from "./api";
import { DIRECTIONS, hexKey, neighbor } from "./hex";
import { oppositeOf, sidesApart } from "./lanes";

export interface LaneTile {
  hex: Axial;
  exits: DirectionName[];
  service: string[];
}

export interface LaneOrderOptions {
  /** Whether lanes run into the hex at this `hexKey` (a planet, or the construction site). */
  isHub: (key: string) => boolean;
}

/** A tile's curve between two of its exits. */
export type Bend = [DirectionName, DirectionName];

export interface CorpTrace {
  /** The exits the corporation's trace reaches. */
  exits: DirectionName[];
  /** The bends it follows between them: one, or a fork of two from a shared stem. */
  bends: Bend[];
}

export interface TileLanes {
  /** The bends the lane itself draws. */
  bends: Bend[];
  /** Each serving corporation's trace. */
  traces: Map<string, CorpTrace>;
}

export interface LaneOrder {
  /** Corporations on each border by `edgeKey`, in order along its canonical normal. */
  orders: Map<string, string[]>;
  /** Each tile's lane and traces, by tile `hexKey`. */
  tiles: Map<string, TileLanes>;
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

function pairKey([a, b]: Bend): string {
  return [a, b].sort().join("-");
}

/**
 * The ways a corporation's trace can join `exits`: one bend between two, otherwise a fork out of
 * each exit in turn to all the others, those with the fewest sharp bends first.
 */
function traceOptions(exits: DirectionName[]): Bend[][] {
  if (exits.length < 2) return [[]];
  if (exits.length === 2) return [[[exits[0], exits[1]]]];
  const sharp = (bends: Bend[]): number => bends.filter(([a, b]) => sidesApart(a, b) === 1).length;
  const forks = exits.map((stem) => exits.filter((exit) => exit !== stem).map((exit): Bend => [stem, exit]));
  return forks.sort((a, b) => sharp(a) - sharp(b));
}

/** Crossings, then lane drift (in half spacings), then sharp bends, then disorder; compared in that order. */
type Cost = [number, number, number, number];

function addCost(total: Cost, more: Cost): void {
  for (let i = 0; i < total.length; i++) total[i] += more[i];
}

function lessThan(a: Cost, b: Cost): boolean {
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return a[i] < b[i];
  }
  return false;
}

/** Twice a corporation's slot offset on a border ordered `corps` (an integer). */
function doubledSlot(corps: string[], corp: string): number {
  return 2 * corps.indexOf(corp) - (corps.length - 1);
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

/** Every order made by moving one item of `items` to another place. */
function moves<T>(items: T[]): T[][] {
  return items.flatMap((item, i) => {
    const rest = [...items.slice(0, i), ...items.slice(i + 1)];
    return [...Array(items.length).keys()].filter((j) => j !== i).map((j) => [...rest.slice(0, j), item, ...rest.slice(j)]);
  });
}

/** Every combination picking one index below each of `counts`. */
function combinations(counts: number[]): number[][] {
  return counts.reduce<number[][]>((partial, count) => partial.flatMap((prefix) => [...Array(count).keys()].map((i) => [...prefix, i])), [[]]);
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

/** A tile in the search: its corporations' trace options and the one each currently follows. */
interface TileState {
  tile: LaneTile;
  corps: { corp: string; exits: DirectionName[]; options: Bend[][] }[];
  choice: number[];
}

/** A chain tries every order of up to this many corporations; of more, every move of one of them. */
const MAX_PERMUTED_CORPS = 5;

/**
 * Two chains meeting at a junction are searched together where they carry at most this many
 * corporations, trying every pair of orders up to the second limit, otherwise every pair of moves.
 */
const MAX_PAIRED_CORPS = 4;
const MAX_PAIRED_PERMUTED_CORPS = 3;

/** A junction tries every combination of its corporations' stems up to this many, then one corporation's at a time. */
const MAX_STEM_COMBINATIONS = 81;

/** Search passes; each pass that changes nothing ends it sooner. */
const MAX_PASSES = 12;

/** Ring positions of the six sides, far enough apart to hold every slot between them. */
const SIDE_SPACING = 100;

/** How corporation traces run across every tile and border of `tiles` (see the module comment). */
export function solveLaneOrder(tiles: LaneTile[], corpIds: string[], options: LaneOrderOptions): LaneOrder {
  const rank = new Map(corpIds.map((corp, i) => [corp, i] as const));
  const byRank = (a: string, b: string): number => (rank.get(a) ?? 0) - (rank.get(b) ?? 0);
  const tilesByKey = new Map(tiles.map((tile) => [hexKey(tile.hex), tile] as const));

  /** Whether `corp` carries on beyond `tile`'s `exit`: into a planet, an open lane end, or a tile it also serves. */
  const carriesOn = (tile: LaneTile, exit: DirectionName, corp: string): boolean => {
    const beyond = neighbor(tile.hex, exit);
    if (options.isHub(hexKey(beyond))) return true;
    const next = tilesByKey.get(hexKey(beyond));
    if (next === undefined || !next.exits.includes(oppositeOf(exit))) return true;
    return next.service.includes(corp);
  };
  /** The exits `corp`'s trace reaches on `tile`: where it carries on, and at least two of them. */
  const reached = (tile: LaneTile, corp: string): DirectionName[] => {
    if (tile.exits.length <= 2) return tile.exits;
    const exits = tile.exits.filter((exit) => carriesOn(tile, exit, corp));
    const others = tile.exits.filter((exit) => !exits.includes(exit));
    // Where it carries on through fewer than two, it still crosses the tile, as gently as it can.
    while (exits.length < 2) {
      const from = exits[0];
      const gentlest = from === undefined ? others[0] : [...others].sort((a, b) => sidesApart(from, b) - sidesApart(from, a))[0];
      exits.push(gentlest);
      others.splice(others.indexOf(gentlest), 1);
    }
    return tile.exits.filter((exit) => exits.includes(exit));
  };

  const states: TileState[] = tiles.map((tile) => {
    const corps = tile.service.map((corp) => {
      const exits = reached(tile, corp);
      return { corp, exits, options: traceOptions(exits) };
    });
    return { tile, corps, choice: corps.map(() => 0) };
  });

  const sets = new Map<string, Set<string>>();
  for (const tile of tiles) {
    for (const exit of tile.exits) {
      const key = edgeKey(tile.hex, exit);
      if (!sets.has(key)) sets.set(key, new Set());
    }
  }
  for (const state of states) {
    for (const { corp, exits } of state.corps) {
      for (const exit of exits) sets.get(edgeKey(state.tile.hex, exit))?.add(corp);
    }
  }
  const corpsOn = (edge: string): string[] => [...(sets.get(edge) ?? [])].sort(byRank);
  const sameCorps = (a: string, b: string): boolean => corpsOn(a).join(" ") === corpsOn(b).join(" ");

  // Through a two-exit tile with the same corporations at both ends, parallel traces need the
  // orders equal where the two normals run opposite ways round the tile, and reversed where they agree.
  const chains = new Chains();
  for (const edge of sets.keys()) chains.add(edge);
  for (const { tile } of states) {
    if (tile.exits.length !== 2 || tile.service.length === 0) continue;
    const [a, b] = tile.exits.map((exit) => edgeKey(tile.hex, exit));
    if (sameCorps(a, b)) chains.join(a, b, normalSign(tile.exits[0]) === normalSign(tile.exits[1]));
  }
  const members = new Map<string, string[]>();
  for (const edge of [...sets.keys()].sort()) {
    const { root } = chains.find(edge);
    members.set(root, [...(members.get(root) ?? []), edge]);
  }
  const rootOrders = new Map([...members.keys()].map((root) => [root, corpsOn(root)] as const));
  const orderOf = (edge: string): string[] => {
    const { root, flipped } = chains.find(edge);
    const order = rootOrders.get(root) ?? [];
    return flipped ? [...order].reverse() : order;
  };

  /** Crossings, drift and sharp bends of a tile's traces as they currently run. */
  const tileCost = (state: TileState): Cost => {
    const { hex, exits } = state.tile;
    // Each corporation's slot on each border, counted clockwise round the tile.
    const clockwise = new Map(
      exits.map((exit) => {
        const order = orderOf(edgeKey(hex, exit));
        return [exit, new Map(order.map((corp) => [corp, normalSign(exit) * doubledSlot(order, corp)] as const))] as const;
      }),
    );
    const slot = (exit: DirectionName, corp: string): number => clockwise.get(exit)?.get(corp) ?? 0;
    const cost: Cost = [0, 0, 0, 0];
    const chords: { corp: string; low: number; high: number }[] = [];
    state.corps.forEach(({ corp, options: forks }, i) => {
      for (const [a, b] of forks[state.choice[i]]) {
        // A trace's side, left of travel from `a` to `b`, is its clockwise slot entering at `a`,
        // and minus that leaving at `b`; it drifts by the difference.
        cost[1] += Math.abs(slot(a, corp) + slot(b, corp));
        if (sidesApart(a, b) === 1) cost[2] += 1;
        const ends = [DIRECTIONS.indexOf(a) * SIDE_SPACING + slot(a, corp), DIRECTIONS.indexOf(b) * SIDE_SPACING + slot(b, corp)];
        chords.push({ corp, low: Math.min(...ends), high: Math.max(...ends) });
      }
    });
    for (let i = 0; i < chords.length; i++) {
      for (let j = i + 1; j < chords.length; j++) {
        const [p, q] = [chords[i], chords[j]];
        if (p.corp !== q.corp && (q.low > p.low && q.low < p.high) !== (q.high > p.low && q.high < p.high)) cost[0] += 1;
      }
    }
    return cost;
  };

  const statesOf = new Map<string, TileState[]>();
  for (const state of states) {
    for (const exit of state.tile.exits) {
      const root = chains.find(edgeKey(state.tile.hex, exit)).root;
      const list = statesOf.get(root) ?? [];
      if (!list.includes(state)) list.push(state);
      statesOf.set(root, list);
    }
  }
  /** The cost of every tile on any of the chains `roots`, and of their borders' disorder. */
  const chainsCost = (...roots: string[]): Cost => {
    const total: Cost = [0, 0, 0, 0];
    for (const state of new Set(roots.flatMap((root) => statesOf.get(root) ?? []))) addCost(total, tileCost(state));
    for (const root of roots) {
      for (const edge of members.get(root) ?? []) total[3] += disorder(orderOf(edge), rank);
    }
    return total;
  };
  /** The orders a chain tries: all of them for few corporations, otherwise every move of one. */
  const ordersToTry = (root: string, most: number): string[][] => {
    const corps = corpsOn(root);
    return corps.length <= most ? permutations(corps) : moves(rootOrders.get(root) ?? corps);
  };
  // Pairs of chains meeting at a junction, searched together: where a corporation forks and
  // another does not, the order on two of its borders may have to change at once.
  const junctionPairs: [string, string][] = [];
  for (const state of states) {
    if (state.tile.exits.length < 3) continue;
    const tileRoots = [...new Set(state.tile.exits.map((exit) => chains.find(edgeKey(state.tile.hex, exit)).root))].filter(
      (root) => corpsOn(root).length > 1 && corpsOn(root).length <= MAX_PAIRED_CORPS,
    );
    for (let i = 0; i < tileRoots.length; i++) {
      for (let j = i + 1; j < tileRoots.length; j++) junctionPairs.push([tileRoots[i], tileRoots[j]]);
    }
  }

  const roots = [...members.keys()].filter((root) => corpsOn(root).length > 1);
  const forking = states.filter((state) => state.corps.some(({ options: forks }) => forks.length > 1));
  for (let pass = 0; pass < MAX_PASSES; pass++) {
    let improved = false;
    for (const root of roots) {
      let best = rootOrders.get(root) ?? [];
      let bestCost = chainsCost(root);
      for (const order of ordersToTry(root, MAX_PERMUTED_CORPS)) {
        rootOrders.set(root, order);
        const cost = chainsCost(root);
        if (lessThan(cost, bestCost)) {
          best = order;
          bestCost = cost;
          improved = true;
        }
      }
      rootOrders.set(root, best);
    }
    for (const [first, second] of junctionPairs) {
      let best = [rootOrders.get(first) ?? [], rootOrders.get(second) ?? []];
      let bestCost = chainsCost(first, second);
      for (const firstOrder of ordersToTry(first, MAX_PAIRED_PERMUTED_CORPS)) {
        for (const secondOrder of ordersToTry(second, MAX_PAIRED_PERMUTED_CORPS)) {
          rootOrders.set(first, firstOrder);
          rootOrders.set(second, secondOrder);
          const cost = chainsCost(first, second);
          if (lessThan(cost, bestCost)) {
            best = [firstOrder, secondOrder];
            bestCost = cost;
            improved = true;
          }
        }
      }
      rootOrders.set(first, best[0]);
      rootOrders.set(second, best[1]);
    }
    for (const state of forking) {
      // Every combination of stems where there are few, otherwise one corporation's at a time.
      const counts = state.corps.map(({ options: forks }) => forks.length);
      const sweeps =
        counts.reduce((product, count) => product * count, 1) <= MAX_STEM_COMBINATIONS
          ? [() => combinations(counts)]
          : counts.map((count, i) => () => [...Array(count).keys()].map((option) => state.choice.map((current, j) => (j === i ? option : current))));
      let bestCost = tileCost(state);
      for (const sweep of sweeps) {
        let best = state.choice;
        for (const choice of sweep()) {
          state.choice = choice;
          const cost = tileCost(state);
          if (lessThan(cost, bestCost)) {
            best = choice;
            bestCost = cost;
            improved = true;
          }
        }
        state.choice = best;
      }
    }
    if (!improved) break;
  }

  const lanes = new Map(states.map((state) => [hexKey(state.tile.hex), tileLanes(state)] as const));
  return { orders: new Map([...sets.keys()].map((edge) => [edge, orderOf(edge)] as const)), tiles: lanes };
}

/** A tile's lane: its corporations' bends, plus the gentlest bend to each exit none of them reaches. */
function tileLanes(state: TileState): TileLanes {
  const { exits } = state.tile;
  const traces = new Map(state.corps.map(({ corp, exits: reaching, options: forks }, i) => [corp, { exits: reaching, bends: forks[state.choice[i]] }] as const));
  const bends = new Map<string, Bend>();
  for (const trace of traces.values()) {
    for (const bend of trace.bends) bends.set(pairKey(bend), bend);
  }
  if (bends.size === 0 && exits.length >= 2) {
    for (const bend of traceOptions(exits)[0]) bends.set(pairKey(bend), bend);
  }
  for (const exit of exits) {
    if ([...bends.values()].some((bend) => bend.includes(exit))) continue;
    const others = exits.filter((other) => other !== exit);
    const gentlest = [...others].sort((a, b) => sidesApart(exit, b) - sidesApart(exit, a))[0];
    if (gentlest !== undefined) bends.set(pairKey([exit, gentlest]), [exit, gentlest]);
  }
  return { bends: [...bends.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, bend]) => bend), traces };
}
