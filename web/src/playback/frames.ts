/**
 * Turns the `moves` a server response carries into display states to animate, each with a
 * summary of what changed and a caption.
 *
 * Everything here is derived by comparing a frame's `after` with the display state before it,
 * rather than re-implementing rules: the server has already applied them.
 */

import type {
  Axial,
  BuyAction,
  CorporationState,
  DeathStarState,
  DirectionName,
  GameState,
  SupplyItem,
  LogEntry,
  MoveFrame,
  Phase,
  Planet,
  TileState,
} from "../api";
import { mergeFacilities, seizedFacilities } from "../facilities";
import type { SeizedFacility } from "../facilities";
import { DIRECTIONS, hexKey, neighbor, sameHex } from "../hex";
import { playerName } from "../selectors";

/**
 * Something the Empire did as a consequence of a move: the end of the round it ended applied a
 * Death Star stage, or the corporation it moved on from went bankrupt. Each gets its own step.
 */
export type EmpireEvent =
  /**
   * `corps` each lost one fleet (or facility); empty when nobody had one. Under the facility rules
   * `taken` names each facility that became Imperial.
   */
  | { type: "seizure"; corps: string[]; taken?: SeizedFacility[] }
  | { type: "site_move"; from: Axial; to: Axial }
  | { type: "launch"; at: Axial }
  | { type: "bankrupt"; corp: string };

/** A corporation's share price before and after a move. */
export interface PriceChange {
  corp: string;
  before: number;
  after: number;
}

/**
 * What a step shows, in the terms the animation layer needs. `newPresident` is the player who
 * took over the presidency in this move, or null when it did not change hands.
 */
export type MoveKind =
  | {
      kind: "buy";
      player: string;
      corp: string;
      source: BuyAction["source"];
      /** Present only when this buy started the corporation, as on the action. */
      par?: number;
      shares: number;
      cost: number;
      /** What the corporation's treasury gained (floating, or incremental capitalization). */
      treasuryGain: number;
      floated: boolean;
      newPresident: string | null;
      price: PriceChange;
    }
  | {
      kind: "sell";
      player: string;
      corp: string;
      count: number;
      proceeds: number;
      price: PriceChange;
      newPresident: string | null;
    }
  /** `priceChanges` holds end-of-round moves, such as a sold-out corporation rising. */
  | { kind: "pass"; player: string; priceChanges: PriceChange[] }
  | { kind: "chart"; corp: string; hex: Axial; exits: DirectionName[]; cost: number }
  | { kind: "upgrade"; corp: string; hex: Axial; exit: DirectionName; cost: number }
  | { kind: "service"; corp: string; hex: Axial; cost: number }
  | { kind: "no_action"; corp: string }
  /** `price` is the supply's fleet price before and after, which rises when a tier sells out. */
  | { kind: "buy_fleet"; corp: string; cost: number; fleets: number; price: PriceChange }
  /**
   * A facility built on `planet` (facility rules): `exit` is the side of the planet whose lane got
   * the new exit, absent when it was left open. `facilities` is how many the builder owns after.
   */
  | {
      kind: "build_facility";
      corp: string;
      planet: string;
      hex: Axial;
      exit?: DirectionName;
      cost: number;
      facilities: number;
      price: PriceChange;
    }
  | { kind: "finish_fleets"; corp: string; fleets: number; item: SupplyItem }
  | {
      kind: "dividend";
      corp: string;
      pay: boolean;
      revenue: number;
      perShare: number;
      /** Cash each player received, by player id; players who got nothing are absent. */
      payouts: Record<string, number>;
      treasuryGain: number;
      price: PriceChange;
    }
  /** A new round began: a banner between moves, not a move. */
  | { kind: "phase"; phase: Phase; roundLabel: string }
  /** What the Empire did after a move (see `EmpireEvent`); a step of its own, not a move. */
  | { kind: "empire"; event: EmpireEvent }
  /** An action this client does not know; captioned from the frame's log. */
  | { kind: "unknown"; actor: string };

export type MoveKindName = MoveKind["kind"];

/** One thing to show during playback, and the display state while it shows. */
export interface PlaybackStep {
  /** The move, or null for a round-change banner. An Empire step carries the move that caused it. */
  frame: MoveFrame | null;
  kind: MoveKind;
  caption: string;
  /** The game just before this move (for a banner, the same as `state`). */
  before: GameState;
  /**
   * The display state to draw during this step. For a move it is the game after the move but
   * still in the move's own phase and turn, so a dividend shows on the dividend view rather
   * than the next corporation's map. A banner shows the new round as it stands.
   */
  state: GameState;
}

/**
 * The display state after `frame`: its `after` merged into `base`. Players keep their names and
 * seat details; corporations are replaced; tiles merge by hex. Nothing is actionable while a
 * replay shows, so legal actions are cleared.
 */
export function applyFrame(base: GameState, frame: MoveFrame): GameState {
  const after = frame.after;
  const updates = new Map(after.players.map((p) => [p.id, p] as const));
  const players = base.players.map((player) => {
    const update = updates.get(player.id);
    if (!update) return player;
    const { cash, worth, shares, certificates } = update;
    return { ...player, cash, worth, shares, certificates };
  });
  return {
    ...base,
    phase: after.phase,
    roundLabel: after.roundLabel,
    roundNumber: after.roundNumber,
    currentPlayer: after.currentPlayer,
    currentCorporation: after.currentCorporation,
    priorityPlayer: after.priorityPlayer,
    operatingOrder: after.operatingOrder,
    networkActionsTaken: after.networkActionsTaken,
    players,
    corporations: after.corporations,
    tiles: mergeTiles(base.tiles, after.tiles),
    deathStar: after.deathStar ?? base.deathStar,
    facilities: mergeFacilities(base.facilities, after.facilities),
    log: appendLog(base.log, frame.log),
    legalActions: [],
    waitingOnHuman: false,
    moves: [],
  };
}

function mergeTiles(base: TileState[], changed: TileState[]): TileState[] {
  if (changed.length === 0) return base;
  const byKey = new Map(changed.map((t) => [hexKey(t.hex), t] as const));
  const merged = base.map((tile) => byKey.get(hexKey(tile.hex)) ?? tile);
  const existing = new Set(base.map((t) => hexKey(t.hex)));
  return [...merged, ...changed.filter((t) => !existing.has(hexKey(t.hex)))];
}

function appendLog(base: LogEntry[], entries: LogEntry[]): LogEntry[] {
  const seen = new Set(base.map((e) => e.seq));
  const fresh = entries.filter((e) => !seen.has(e.seq));
  return fresh.length === 0 ? base : [...base, ...fresh];
}

/**
 * `applied` (the game after `frame`) shown in the move's own phase and turn: whose move it was,
 * and the round it was made in. Holdings, prices and the map are as after the move.
 */
export function stagedState(prev: GameState, applied: GameState, frame: MoveFrame): GameState {
  const sameTurn = applied.phase === frame.phase && applied.currentCorporation === frame.corporation;
  // A corporation's last network action moves the game on to its dividend, so `applied` no
  // longer holds the count; carry it from the step before instead.
  const continuing = prev.phase === "network" && prev.currentCorporation === frame.corporation;
  const networkActionsTaken =
    frame.phase === "network"
      ? (continuing ? prev.networkActionsTaken : 0) + 1
      : sameTurn
        ? applied.networkActionsTaken
        : prev.networkActionsTaken;
  return {
    ...applied,
    phase: frame.phase,
    roundLabel: frame.roundLabel,
    roundNumber: prev.roundNumber,
    currentPlayer: frame.actor,
    currentCorporation: frame.corporation,
    operatingOrder: prev.operatingOrder,
    priorityPlayer: prev.priorityPlayer,
    networkActionsTaken,
    legalActions: [],
    waitingOnHuman: false,
  };
}

/**
 * The steps to play between `before` (what the client showed) and `after` (the server's reply):
 * one per automatic move, plus a banner wherever the round changes. The submitted move is not
 * shown, since its player just made it, but it is applied so the first automatic move starts
 * from the right state. Once the steps have played, the client shows `after` itself.
 *
 * `planets` (from the board) let captions name the planet a hex is at or next to.
 */
export function playbackSteps(before: GameState, after: GameState, planets: Planet[] = []): PlaybackStep[] {
  // Servers from before move frames send no `moves`.
  const frames = after.moves ?? [];
  const steps: PlaybackStep[] = [];
  let state = before;
  frames.forEach((frame, i) => {
    const prev = state;
    state = i === frames.length - 1 ? after : applyFrame(prev, frame);
    const staged = stagedState(prev, state, frame);
    if (frame.automatic) {
      const kind = moveKind(frame, prev);
      const caption = describeKind(kind, frame, prev, planets) + trackNote(prev.deathStar, frame.after.deathStar);
      steps.push({ frame, kind, caption, before: prev, state: staged });
    }
    // The Empire's doings show even after the player's own move, since nobody chose them.
    for (const event of empireEvents(prev, frame)) {
      const kind: MoveKind = { kind: "empire", event };
      steps.push({ frame, kind, caption: describeEmpire(event, prev, planets), before: prev, state: staged });
    }
    if (state.roundLabel !== prev.roundLabel) {
      const kind: MoveKind = { kind: "phase", phase: state.phase, roundLabel: state.roundLabel };
      steps.push({ frame: null, kind, caption: roundTitle(state.phase, state.roundLabel), before: state, state });
    }
  });
  return steps;
}

/**
 * The display states to animate: one per automatic move (and round banner), then `after`
 * itself. With no automatic moves (or a server that sends none) it is just `[after]`.
 */
export function displayStates(before: GameState, after: GameState): GameState[] {
  return [...playbackSteps(before, after).map((step) => step.state), after];
}

function corpIn(corporations: CorporationState[], corpId: string): CorporationState | undefined {
  return corporations.find((c) => c.id === corpId);
}

function cashOf(players: { id: string; cash: number }[], playerId: string): number {
  return players.find((p) => p.id === playerId)?.cash ?? 0;
}

function sharesOf(players: { id: string; shares: Record<string, number> }[], playerId: string, corpId: string): number {
  return players.find((p) => p.id === playerId)?.shares[corpId] ?? 0;
}

function presidentChange(before: CorporationState, after: CorporationState): string | null {
  return after.president !== before.president && after.president !== "" ? after.president : null;
}

/** Summarises `frame` by comparing its `after` with `prev`, the display state before it. */
export function moveKind(frame: MoveFrame, prev: GameState): MoveKind {
  const action = frame.action;
  const after = frame.after;
  const unknown: MoveKind = { kind: "unknown", actor: frame.actor };
  const corpId =
    "corp" in action ? action.corp : (frame.corporation ?? prev.currentCorporation ?? "");
  const corpBefore = corpIn(prev.corporations, corpId);
  const corpAfter = corpIn(after.corporations, corpId);
  if (action.type === "pass") {
    const priceChanges = after.corporations.flatMap((c) => {
      const old = corpIn(prev.corporations, c.id);
      return old && old.price !== c.price ? [{ corp: c.id, before: old.price, after: c.price }] : [];
    });
    return { kind: "pass", player: frame.actor, priceChanges };
  }
  if (!corpBefore || !corpAfter) return unknown;
  if (action.type === "buy_fleet") {
    const supply = (ds: DeathStarState | undefined) => ds?.fleets.price ?? action.cost;
    return {
      kind: "buy_fleet",
      corp: corpId,
      cost: corpBefore.treasury - corpAfter.treasury,
      fleets: corpAfter.fleets,
      price: { corp: corpId, before: supply(prev.deathStar), after: supply(after.deathStar) },
    };
  }
  if (action.type === "build_facility") {
    const supply = (ds: DeathStarState | undefined) => ds?.fleets.price ?? action.cost;
    const planet = prev.facilities?.planets.find((p) => sameHex(p.hex, action.planet))?.name ?? formatHex(action.planet);
    return {
      kind: "build_facility",
      corp: corpId,
      planet,
      hex: action.planet,
      ...(action.exit ? { exit: action.exit } : {}),
      cost: corpBefore.treasury - corpAfter.treasury,
      facilities: corpAfter.fleets,
      price: { corp: corpId, before: supply(prev.deathStar), after: supply(after.deathStar) },
    };
  }
  if (action.type === "finish_fleets") {
    return { kind: "finish_fleets", corp: corpId, fleets: corpAfter.fleets, item: prev.deathStar?.fleets.item ?? "fleet" };
  }
  const price: PriceChange = { corp: corpId, before: corpBefore.price, after: corpAfter.price };
  const player = frame.actor;
  switch (action.type) {
    case "buy":
      return {
        kind: "buy",
        player,
        corp: corpId,
        source: action.source,
        ...(action.par !== undefined ? { par: action.par } : {}),
        shares: sharesOf(after.players, player, corpId) - sharesOf(prev.players, player, corpId),
        cost: cashOf(prev.players, player) - cashOf(after.players, player),
        treasuryGain: corpAfter.treasury - corpBefore.treasury,
        floated: corpBefore.status !== "floated" && corpAfter.status === "floated",
        newPresident: presidentChange(corpBefore, corpAfter),
        price,
      };
    case "sell":
      return {
        kind: "sell",
        player,
        corp: corpId,
        count: action.count,
        proceeds: cashOf(after.players, player) - cashOf(prev.players, player),
        price,
        newPresident: presidentChange(corpBefore, corpAfter),
      };
    case "chart":
    case "upgrade":
    case "service": {
      const cost = corpBefore.treasury - corpAfter.treasury;
      if (action.type === "chart") return { kind: "chart", corp: corpId, hex: action.hex, exits: action.exits, cost };
      if (action.type === "upgrade") return { kind: "upgrade", corp: corpId, hex: action.hex, exit: action.exit, cost };
      return { kind: "service", corp: corpId, hex: action.hex, cost };
    }
    case "no_action":
      return { kind: "no_action", corp: corpId };
    case "dividend":
      return dividendKind(frame, prev, corpBefore, corpAfter, price);
    default:
      return unknown;
  }
}

function dividendKind(
  frame: MoveFrame,
  prev: GameState,
  corpBefore: CorporationState,
  corpAfter: CorporationState,
  price: PriceChange,
): MoveKind {
  const payouts: Record<string, number> = {};
  let perShare = 0;
  for (const player of frame.after.players) {
    const gained = player.cash - cashOf(prev.players, player.id);
    if (gained <= 0) continue;
    payouts[player.id] = gained;
    const held = player.shares[corpBefore.id] ?? 0;
    if (held > 0) perShare = gained / held;
  }
  return {
    kind: "dividend",
    corp: corpBefore.id,
    pay: frame.action.type === "dividend" && frame.action.choice === "pay" && frame.revenue > 0,
    revenue: frame.revenue,
    perShare,
    payouts,
    treasuryGain: corpAfter.treasury - corpBefore.treasury,
    price,
  };
}

/**
 * What the Empire did in `frame`, found by comparing its `after` with `prev`: bankruptcies, then
 * each Death Star stage result that applied, in order.
 */
export function empireEvents(prev: GameState, frame: MoveFrame): EmpireEvent[] {
  const after = frame.after;
  const events: EmpireEvent[] = [];
  for (const corp of after.corporations) {
    const before = corpIn(prev.corporations, corp.id);
    if (corp.status === "closed" && before && before.status !== "closed") events.push({ type: "bankrupt", corp: corp.id });
  }
  const from = prev.deathStar;
  const to = after.deathStar;
  if (!from || !to) return events;
  for (let index = from.stage; index < to.stage; index += 1) {
    const result = to.stages[index]?.result;
    if (result === "seizure") {
      const corps = after.corporations
        .filter((c) => {
          const before = corpIn(prev.corporations, c.id);
          return before !== undefined && c.fleets < before.fleets;
        })
        .map((c) => c.id);
      if (after.facilities) {
        events.push({ type: "seizure", corps, taken: seizedFacilities(prev.facilities, after.facilities) });
      } else {
        events.push({ type: "seizure", corps });
      }
    } else if (result === "move") {
      const old = from.sites.find((site) => site.status === "active");
      const next = to.sites.find((site) => site.status === "active") ?? to.sites.find((site) => site.status === "launched");
      if (old && next) events.push({ type: "site_move", from: old.hex, to: next.hex });
    } else if (result === "completion") {
      const site = to.sites.find((s) => s.status === "launched");
      if (site) events.push({ type: "launch", at: site.hex });
    }
  }
  return events;
}

/** "; +1 Death Star cube (7/24)", with any stage it filled; empty when the track did not move. */
export function trackNote(before: DeathStarState | undefined, after: DeathStarState | undefined): string {
  if (!before || !after || after.cubes <= before.cubes) return "";
  const added = after.cubes - before.cubes;
  const filled = after.stages
    .filter((stage, i) => stage.filled && !before.stages[i]?.filled)
    .map((stage) => `; ${stage.name} stage complete`);
  return `; +${added} Death Star ${added === 1 ? "cube" : "cubes"} (${after.cubes}/${after.totalCubes})${filled.join("")}`;
}

function describeEmpire(event: EmpireEvent, prev: GameState, planets: Planet[]): string {
  switch (event.type) {
    case "seizure":
      if (event.taken) {
        const taken = event.taken.map((f, i) => `${f.corp}'s ${i === 0 ? "facility " : ""}at ${f.planet}`);
        return taken.length > 0
          ? `The Empire takes over ${listText(taken)}; ${taken.length === 1 ? "it is" : "they are"} Imperial now`
          : "The Empire finds no facilities to take over";
      }
      return event.corps.length > 0
        ? `The Empire seizes a fleet from ${event.corps.join(", ")}`
        : "The Empire finds no fleets to seize";
    case "site_move":
      return `The Death Star site moves from ${describeHex(event.from, planets)} to ${describeHex(event.to, planets)}; the old site is empty space`;
    case "launch":
      return "The Death Star launches! The game ends after this round";
    case "bankrupt": {
      const president = corpIn(prev.corporations, event.corp)?.president ?? "";
      const owner = president ? ` (${playerName(prev, president)})` : "";
      const reason = prev.facilities ? "no facility, and none it can build" : "no fleet, and no money for one";
      return `${event.corp}${owner} is bankrupt: ${reason}. It closes and its shares are worthless`;
    }
  }
}

/** "A", "A and B", "A, B and C". */
function listText(items: string[]): string {
  return items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/** "(−3,1)", with a typographic minus. */
export function formatHex(hex: Axial): string {
  return `(${hex.map((n) => String(n).replace("-", "−")).join(",")})`;
}

/** Where a hex is, for a caption: "Kuat (−3,1)", "(−3,1) near Kuat", or just "(−3,1)". */
export function describeHex(hex: Axial, planets: Planet[]): string {
  const at = planets.find((p) => sameHex(p.hex, hex));
  if (at) return `${at.name} ${formatHex(hex)}`;
  const near = planets.find((p) => DIRECTIONS.some((d) => sameHex(neighbor(hex, d), p.hex)));
  return near ? `${formatHex(hex)} near ${near.name}` : formatHex(hex);
}

function priceText(change: PriceChange): string {
  return change.before === change.after
    ? `price stays ${change.after}`
    : `price ${change.before} → ${change.after}`;
}

/** "Stock round 2", "Operating round 1.2", "Game over". */
export function roundTitle(phase: Phase, roundLabel: string): string {
  if (phase === "game_over") return "Game over";
  const match = /^(SR|OR)(.+)$/.exec(roundLabel);
  if (!match) return roundLabel;
  return `${match[1] === "SR" ? "Stock round" : "Operating round"} ${match[2]}`;
}

/** A short caption for `frame`, given the display state before it. */
export function describeMove(frame: MoveFrame, prev: GameState, planets: Planet[] = []): string {
  return describeKind(moveKind(frame, prev), frame, prev, planets);
}

function describeKind(kind: MoveKind, frame: MoveFrame | null, prev: GameState, planets: Planet[]): string {
  const name = (id: string) => playerName(prev, id);
  const president = (id: string | null) => (id === null ? "" : `; ${name(id)} becomes president`);
  switch (kind.kind) {
    case "buy": {
      const floats = kind.floated ? `; ${kind.corp} floats` : "";
      if (kind.par !== undefined) {
        return `${name(kind.player)} starts ${kind.corp} at par ${kind.par}${floats}`;
      }
      const from = kind.source === "ipo" ? "the IPO" : "the pool";
      return `${name(kind.player)} buys a ${kind.corp} share from ${from} for ${kind.cost}${president(kind.newPresident)}${floats}`;
    }
    case "sell":
      return `${name(kind.player)} sells ${kind.count} ${kind.corp} for ${kind.proceeds}; ${priceText(kind.price)}${president(kind.newPresident)}`;
    case "pass": {
      const soldOut = kind.priceChanges.map((c) => `; ${c.corp} sold out, ${priceText(c)}`).join("");
      return `${name(kind.player)} passes${soldOut}`;
    }
    case "chart":
      return `${kind.corp} charts a lane at ${describeHex(kind.hex, planets)} for ${kind.cost}`;
    case "upgrade":
      return `${kind.corp} adds a ${kind.exit} exit at ${describeHex(kind.hex, planets)} for ${kind.cost}`;
    case "service":
      return `${kind.corp} extends service to ${describeHex(kind.hex, planets)} for ${kind.cost}`;
    case "no_action":
      return `${kind.corp} takes no network action`;
    case "buy_fleet": {
      const rise = kind.price.after !== kind.price.before ? `; fleets now cost ${kind.price.after}` : "";
      return `${kind.corp} buys a fleet for ${kind.cost}, owning ${kind.fleets}${rise}`;
    }
    case "build_facility": {
      const lane = kind.exit ? `, giving its new exit to the ${kind.exit} lane` : ", leaving its new exit open";
      const rise = kind.price.after !== kind.price.before ? `; facilities now cost ${kind.price.after}` : "";
      return `${kind.corp} builds a facility at ${kind.planet} for ${kind.cost}${lane}, owning ${kind.facilities}${rise}`;
    }
    case "finish_fleets":
      return kind.item === "facility"
        ? `${kind.corp} runs ${kind.fleets} ${kind.fleets === 1 ? "facility" : "facilities"}`
        : `${kind.corp} runs ${kind.fleets} ${kind.fleets === 1 ? "fleet" : "fleets"}`;
    case "empire":
      return describeEmpire(kind.event, prev, planets);
    case "dividend":
      if (kind.pay) {
        return `${kind.corp} pays ${kind.revenue} — ${kind.perShare} per share; ${priceText(kind.price)}`;
      }
      if (kind.revenue === 0) return `${kind.corp} earns nothing; ${priceText(kind.price)}`;
      return `${kind.corp} withholds ${kind.revenue}; ${priceText(kind.price)}`;
    case "phase":
      return roundTitle(kind.phase, kind.roundLabel);
    case "unknown": {
      const lines = frame?.log.map((e) => `${e.actor} ${e.text}`) ?? [];
      return lines.length > 0 ? lines.join("; ") : `${name(kind.actor)} moves`;
    }
  }
}
