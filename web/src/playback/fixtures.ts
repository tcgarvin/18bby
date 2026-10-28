/**
 * Small hand-built game states and move frames for the playback tests, shaped after real API
 * responses (three seats, two corporations).
 */

import type {
  Action,
  CorporationState,
  DeathStarState,
  FrameState,
  GameState,
  LogEntry,
  MoveFrame,
  PlanetFacilities,
  PlayerState,
  TileState,
} from "../api";

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
    fleets: 0,
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
    buyBlocks: {},
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

/**
 * The frame view of `state`, as the server would send it for a move that changed `tiles` (and,
 * under the facility rules, `planets`).
 */
export function frameState(state: GameState, tiles: TileState[] = [], planets: PlanetFacilities[] = []): FrameState {
  const facilities = state.facilities;
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
    ...(state.deathStar ? { deathStar: state.deathStar } : {}),
    ...(facilities
      ? { facilities: { perPlanet: facilities.perPlanet, planets, seizureTargets: facilities.seizureTargets } }
      : {}),
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
  /** Under the facility rules, the planets the move changed. */
  planets?: PlanetFacilities[];
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
    after: frameState(after, options.tiles ?? [], options.planets ?? []),
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

/** A Death Star track at its start, shaped like the server's: four stages of six cubes. */
export function deathStarState(overrides: Partial<DeathStarState> = {}): DeathStarState {
  return {
    siteName: "Death Star",
    siteTag: "W",
    contractPartnerTags: ["I", "R", "S"],
    sites: [
      { hex: [6, -2], region: "Outer Rim", status: "active" },
      { hex: [-1, 5], region: "Mid Rim", status: "reserved" },
    ],
    cubes: 0,
    cubesPerStage: 6,
    totalCubes: 24,
    stages: [
      { name: "Frame", value: 40, result: "seizure", filled: false, resolved: false },
      { name: "Superstructure", value: 50, result: "move", filled: false, resolved: false },
      { name: "Superlaser", value: 60, result: "seizure", filled: false, resolved: false },
      { name: "Completion", value: 70, result: "completion", filled: false, resolved: false },
    ],
    stage: 0,
    contractValue: 40,
    launched: false,
    finalRound: 8,
    backstopRound: 8,
    empireCubesPerStockRound: 1,
    fleets: {
      item: "fleet",
      price: 60,
      tier: 0,
      remainingInTier: 6,
      tiers: [
        { price: 60, count: 6, remaining: 6 },
        { price: 90, count: 6, remaining: 6 },
        { price: 120, count: 6, remaining: 6 },
        { price: 160, count: "unlimited", remaining: "unlimited" },
      ],
      limit: 4,
      sold: 0,
    },
    ...overrides,
  };
}

/** `deathStar` with `cubes` on the track and the stages before `stage` resolved. */
export function trackAt(deathStar: DeathStarState, cubes: number, stage: number): DeathStarState {
  return {
    ...deathStar,
    cubes,
    stage,
    stages: deathStar.stages.map((s, i) => ({ ...s, filled: cubes >= (i + 1) * deathStar.cubesPerStage, resolved: i < stage })),
    contractValue: deathStar.stages[stage]?.value ?? 0,
  };
}

/** A planet under the facility rules: one open exit and no facilities, unless overridden. */
export function planetFacilities(name: string, hex: [number, number], overrides: Partial<PlanetFacilities> = {}): PlanetFacilities {
  return { hex, name, exits: 1, claimed: [], unclaimed: 1, dangling: [], facilities: [], freeSlots: 2, ...overrides };
}

/**
 * `state` under the facility rules: the supply sells facilities and the planets are `planets`
 * (Corellia, home of CEC with its free facility, and Kuat, by default).
 */
export function withFacilities(state: GameState, planets?: PlanetFacilities[]): GameState {
  const deathStar = state.deathStar ?? deathStarState();
  return {
    ...state,
    deathStar: { ...deathStar, fleets: { ...deathStar.fleets, item: "facility" } },
    facilities: {
      perPlanet: 2,
      planets: planets ?? [
        planetFacilities("Corellia", [-5, 3], { exits: 2, unclaimed: 2, facilities: [{ owner: "CEC", build: 0 }], freeSlots: 1 }),
        planetFacilities("Kuat", [-3, 2]),
      ],
      seizureTargets: [],
      options: [],
    },
  };
}
