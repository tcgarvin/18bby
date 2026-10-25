/**
 * Small hand-built game states and move frames for the playback tests, shaped after real API
 * responses (three seats, two corporations).
 */

import type { Action, CorporationState, FrameState, GameState, LogEntry, MoveFrame, PlayerState, TileState } from "../api";

export function corporation(id: string, overrides: Partial<CorporationState> = {}): CorporationState {
  return {
    id,
    name: `${id} Corporation`,
    homeworld: "Corellia",
    status: "unstarted",
    par: 0,
    ipoPrice: 0,
    price: 0,
    marketCell: null,
    dividendPreview: null,
    treasury: 0,
    ipoShares: 10,
    poolShares: 0,
    president: "",
    lastRevenue: 0,
    reachablePlanets: [],
    revenue: { total: 0, pairs: [] },
    ...overrides,
  };
}

export function player(id: string, name: string, overrides: Partial<PlayerState> = {}): PlayerState {
  return {
    id,
    name,
    cash: 400,
    worth: 400,
    shares: {},
    isBot: id !== "P1",
    difficulty: id === "P1" ? "" : "easy",
    plan: "",
    certificates: 0,
    ...overrides,
  };
}

export function gameState(overrides: Partial<GameState> = {}): GameState {
  return {
    phase: "stock",
    roundLabel: "SR1",
    roundNumber: 1,
    totalRounds: 6,
    currentPlayer: "P1",
    currentCorporation: null,
    waitingOnHuman: true,
    legalActions: [{ type: "pass" }],
    players: [player("P1", "Tim"), player("P2", "Selka Darrow"), player("P3", "Admiral Rax")],
    priorityPlayer: "P1",
    corporations: [corporation("CEC"), corporation("KDY")],
    operatingOrder: [],
    tiles: [],
    terrain: [],
    stockMarket: [[60, 70, 80, 90, 100]],
    parColumn: 1,
    networkActionsTaken: 0,
    canUndo: false,
    automaticLogStart: 0,
    config: {
      chartCost: 60,
      upgradeCost: 80,
      serviceCost: 60,
      nebulaChartSurcharge: 20,
      networkActionsPerTurn: 2,
      parPrices: [60, 70, 80, 90],
      sharesPerCorporation: 10,
      certificateLimit: 12,
      maxHoldingShares: 6,
      typedPairValue: 30,
      regionalBonus: 10,
      basicRouteValue: 10,
    },
    log: [],
    moves: [],
    ...overrides,
  };
}

export function logEntry(seq: number, actor: string, text: string, round = "SR1"): LogEntry {
  return { seq, round, actor, text };
}

/** The frame view of `state`, as the server would send it for a move that changed `tiles`. */
export function frameState(state: GameState, tiles: TileState[] = []): FrameState {
  return {
    phase: state.phase,
    roundLabel: state.roundLabel,
    roundNumber: state.roundNumber,
    currentPlayer: state.currentPlayer,
    currentCorporation: state.currentCorporation,
    priorityPlayer: state.priorityPlayer,
    operatingOrder: state.operatingOrder,
    networkActionsTaken: state.networkActionsTaken,
    players: state.players.map(({ id, cash, worth, shares, certificates }) => ({ id, cash, worth, shares, certificates })),
    corporations: state.corporations,
    tiles,
  };
}

export interface FrameOptions {
  actor: string;
  /** The phase the move was made in; defaults to the phase after it. */
  phase?: MoveFrame["phase"];
  automatic?: boolean;
  corporation?: string | null;
  log?: LogEntry[];
  revenue?: number;
  tiles?: TileState[];
}

/** A frame for `action` that leaves the game as `after`. */
export function moveFrame(action: Action, after: GameState, options: FrameOptions): MoveFrame {
  return {
    phase: options.phase ?? (after.phase === "game_over" ? "dividend" : after.phase),
    roundLabel: after.roundLabel,
    actor: options.actor,
    corporation: options.corporation ?? null,
    action,
    automatic: options.automatic ?? true,
    log: options.log ?? [],
    revenue: options.revenue ?? 0,
    after: frameState(after, options.tiles ?? []),
  };
}

/** `state` with one player's fields changed. */
export function withPlayer(state: GameState, id: string, changes: Partial<PlayerState>): GameState {
  return { ...state, players: state.players.map((p) => (p.id === id ? { ...p, ...changes } : p)) };
}

/** `state` with one corporation's fields changed. */
export function withCorp(state: GameState, id: string, changes: Partial<CorporationState>): GameState {
  return { ...state, corporations: state.corporations.map((c) => (c.id === id ? { ...c, ...changes } : c)) };
}
