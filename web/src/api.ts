/**
 * Types and fetch helpers for the 18BBY JSON API (see src/bby18/api/serialize.py).
 *
 * Clients never construct actions: every action submitted is one of `state.legalActions`,
 * echoed back verbatim, because the server matches by structural equality.
 */

import { accessToken } from "./auth";

export type Axial = [number, number];

export type Region = "Core" | "Mid Rim" | "Outer Rim";
export const REGIONS: Region[] = ["Core", "Mid Rim", "Outer Rim"];

export type DirectionName = "E" | "SE" | "SW" | "W" | "NW" | "NE";

export interface Planet {
  name: string;
  hex: Axial;
  region: Region;
  tags: string[];
}

export interface Board {
  radius: number;
  hexes: Axial[];
  planets: Planet[];
}

export type Phase = "stock" | "network" | "fleet" | "dividend" | "game_over";

/** "closed": bankrupt under the Death Star rules; its shares have left the game. */
export type CorpStatus = "unstarted" | "parred" | "floated" | "closed";

export interface PassAction {
  type: "pass";
}
export interface BuyAction {
  type: "buy";
  corp: string;
  source: "ipo" | "pool";
  par?: number;
}
export interface SellAction {
  type: "sell";
  corp: string;
  count: number;
}
export interface ChartAction {
  type: "chart";
  hex: Axial;
  exits: DirectionName[];
  cost: number;
}
export interface UpgradeAction {
  type: "upgrade";
  hex: Axial;
  exit: DirectionName;
  cost: number;
}
export interface ServiceAction {
  type: "service";
  hex: Axial;
  cost: number;
}
export interface NoNetworkAction {
  type: "no_action";
}
export interface DividendAction {
  type: "dividend";
  choice: "pay" | "withhold";
}
/** Buy one fleet at the supply's current price (Death Star rules). */
export interface BuyFleetAction {
  type: "buy_fleet";
  cost: number;
}
/** End the fleet step (the facility step under the facility rules); offered once the corporation owns one. */
export interface FinishFleetsAction {
  type: "finish_fleets";
}
/**
 * Build one facility on `planet` at the supply's current price (facility rules). The planet gains
 * an exit: given to the lane on side `exit` of the planet (one that dangles there), or, when
 * `exit` is absent, left unclaimed for the next tile charted toward the planet.
 */
export interface BuildFacilityAction {
  type: "build_facility";
  planet: Axial;
  exit?: DirectionName;
  cost: number;
}

export type Action =
  | PassAction
  | BuyAction
  | SellAction
  | ChartAction
  | UpgradeAction
  | ServiceAction
  | NoNetworkAction
  | BuyFleetAction
  | FinishFleetsAction
  | BuildFacilityAction
  | DividendAction;

export type HexAction = ChartAction | UpgradeAction | ServiceAction;

export interface PlayerState {
  id: string;
  name: string;
  cash: number;
  worth: number;
  shares: Record<string, number>;
  isBot: boolean;
  /** A bot seat's difficulty; empty for humans and for bots from before difficulties. */
  difficulty: string;
  /** The bot character's strategy in plain words, revealed when the game is over; else empty. */
  plan: string;
  certificates: number;
}

export interface RevenuePair {
  a: string;
  b: string;
  value: number;
  typed: boolean;
  /** A Death Star contract pair: the construction site with a partner planet. */
  contract: boolean;
}

/** Revenue with more fleets than the corporation owns (Death Star rules). */
export interface FleetRevenue {
  /** Revenue with one more fleet than it owns now. */
  withNextFleet: number;
  /** Revenue with no fleet limit at all, and how many pairs that runs. */
  uncapped: number;
  uncappedPairs: number;
}

export interface CorporationState {
  id: string;
  name: string;
  homeworld: string;
  status: CorpStatus;
  par: number;
  /** What one IPO share costs now (par, or more under an experimental IPO price rule). */
  ipoPrice: number;
  price: number;
  /** [row, column] on the stock market, or null before the corporation starts. */
  marketCell: [number, number] | null;
  /** Share price after paying or withholding this turn's revenue; null until floated. */
  dividendPreview: { pay: number; withhold: number } | null;
  treasury: number;
  ipoShares: number;
  poolShares: number;
  /** Player id, or "" when the corporation has no president yet. */
  president: string;
  lastRevenue: number;
  /**
   * Fleets owned; each runs one revenue pair. Always 0 without the Death Star rules. Under the
   * facility rules, the facilities it owns (each runs one pair just the same).
   */
  fleets: number;
  reachablePlanets: string[];
  revenue: { total: number; pairs: RevenuePair[] };
  /** Present only under the Death Star rules. */
  fleetRevenue?: FleetRevenue;
}

/** What happens when a Death Star stage fills. */
export type StageResult = "seizure" | "move" | "completion";

/** A construction site and where it stands. Vacated and launched hexes are empty space again. */
export interface DeathStarSite {
  hex: Axial;
  region: Region;
  status: "active" | "reserved" | "vacated" | "launched" | "unused";
}

export interface DeathStarStage {
  name: string;
  /** What a contract pair scores while this stage is being built. */
  value: number;
  result: StageResult;
  /** All its cubes are on the track. */
  filled: boolean;
  /** Its result has applied (at the end of the round it filled in). */
  resolved: boolean;
}

/** What a corporation buys for pair capacity: fleets, or facilities under the facility rules. */
export type SupplyItem = "fleet" | "facility";

/** A fleet price tier; "unlimited" for the last, which never sells out. */
export interface FleetTierState {
  price: number;
  count: number | "unlimited";
  remaining: number | "unlimited";
}

/** The Death Star track, its construction sites and the shared fleet supply. */
export interface DeathStarState {
  /** The active site's planet name and tag, for the map and revenue pairs. */
  siteName: string;
  siteTag: string;
  contractPartnerTags: string[];
  sites: DeathStarSite[];
  cubes: number;
  cubesPerStage: number;
  totalCubes: number;
  stages: DeathStarStage[];
  /** Index of the stage being built: the number resolved (equal to stages.length after launch). */
  stage: number;
  /** What a contract pair scores now; 0 once the station has launched. */
  contractValue: number;
  launched: boolean;
  /** The game ends after this round: the backstop, or the launch round. */
  finalRound: number;
  backstopRound: number;
  empireCubesPerStockRound: number;
  fleets: {
    /** What the supply sells: fleets, or facilities under the facility rules (same tiers and limit). */
    item: SupplyItem;
    price: number;
    /** Index in `tiers` of the tier the next fleet comes from. */
    tier: number;
    remainingInTier: number | "unlimited";
    tiers: FleetTierState[];
    limit: number;
    sold: number;
  };
}

/** Owner of a facility the Empire has taken over. */
export const EMPIRE = "Empire";

/** One facility on a planet (facility rules). */
export interface FacilityState {
  /** A corporation id, or `EMPIRE` once seized. */
  owner: string;
  /** Order of building over the game, from 0: a later facility has a higher number. */
  build: number;
}

/** A planet's exits and facilities under the facility rules. The Death Star site is never listed: it keeps every exit. */
export interface PlanetFacilities {
  hex: Axial;
  name: string;
  /** Exits it has, claimed or not: one, plus one per facility. */
  exits: number;
  /** Sides that lanes have claimed; the planet connects only through these. */
  claimed: DirectionName[];
  /** Exits no lane has claimed yet; the next tile charted toward the planet takes one. */
  unclaimed: number;
  /** Sides where a charted lane faces the planet without an exit: it does not connect. */
  dangling: DirectionName[];
  /** Oldest first. */
  facilities: FacilityState[];
  /** Facilities a floated corporation may still build here (a slot is kept on an unfloated homeworld). */
  freeSlots: number;
}

/** What one legal facility build would do for the corporation building it. */
export interface FacilityOption {
  /** One of `legalActions`, unchanged. */
  action: BuildFacilityAction;
  /** Its revenue with this facility: one more pair, over the network the new exit gives it. */
  revenue: number;
  /** Planets the new exit's lane would newly connect it to. */
  reaches: string[];
  /** Corporations with service on the lane the new exit is given to; empty when left unclaimed. */
  lane: string[];
}

/** The facility rules' state. */
export interface FacilitiesState {
  /** Most facilities, corporate or Imperial, one planet may hold. */
  perPlanet: number;
  /** Every planet with limited exits. In a move frame, only those the move changed. */
  planets: PlanetFacilities[];
  /** The facility the next seizure would take from each corporation that owns one: the one nearest the site. */
  seizureTargets: { corp: string; hex: Axial }[];
  /** During the operating corporation's facility step, each legal build and what it would do; else empty. */
  options: FacilityOption[];
}

export interface TileState {
  hex: Axial;
  exits: DirectionName[];
  service: string[];
}

export type TerrainKind = "asteroid" | "nebula";

/** A hex that is not plain space. Terrain is laid out per game from its seed. */
export interface TerrainHex {
  hex: Axial;
  kind: TerrainKind;
}

export interface LogEntry {
  seq: number;
  round: string;
  actor: string;
  text: string;
}

export interface GameConfig {
  chartCost: number;
  upgradeCost: number;
  serviceCost: number;
  /** Extra cost, on top of `chartCost`, to chart a nebula hex. */
  nebulaChartSurcharge: number;
  networkActionsPerTurn: number;
  parPrices: number[];
  sharesPerCorporation: number;
  certificateLimit: number;
  maxHoldingShares: number;
  typedPairValue: number;
  regionalBonus: number;
  basicRouteValue: number;
}

export interface GameState {
  phase: Phase;
  roundLabel: string;
  roundNumber: number;
  totalRounds: number;
  currentPlayer: string | null;
  currentCorporation: string | null;
  waitingOnHuman: boolean;
  legalActions: Action[];
  players: PlayerState[];
  priorityPlayer: string;
  corporations: CorporationState[];
  /**
   * Corporation ids in operating order. During an operating round it is the queue fixed when
   * the round began (it does not re-sort as prices move); otherwise, the next round's order.
   */
  operatingOrder: string[];
  tiles: TileState[];
  /** Asteroid fields and nebulae; hexes not listed are plain space. */
  terrain: TerrainHex[];
  /** Market rows, top (highest prices) first; lower rows may be shorter. */
  stockMarket: number[][];
  parColumn: number;
  /** Network actions the operating corporation has already taken this turn. */
  networkActionsTaken: number;
  /** Whether the last submitted action can be taken back. */
  canUndo: boolean;
  /** Log entries with this seq or later were played automatically (bots or forced moves). */
  automaticLogStart: number;
  config: GameConfig;
  /** The Death Star track and fleet supply; absent when the game is played without those rules. */
  deathStar?: DeathStarState;
  /** Planet exits and facilities; present only under the facility rules. */
  facilities?: FacilitiesState;
  log: LogEntry[];
  /**
   * Every move played by the request that produced this state, in order: the submitted move
   * first (automatic: false), then each bot or forced move after it. Empty on a plain load or
   * an undo; on a new game it holds any opening bot moves. Clients replay these to animate
   * what opponents did.
   */
  moves: MoveFrame[];
}

/** One move, and the parts of the game state it can change, as they stood just after it. */
export interface MoveFrame {
  /** The phase the move was made in, and the round label then. */
  phase: Exclude<Phase, "game_over">;
  roundLabel: string;
  /** Player id of whoever made the move (a corporation's president in operating rounds). */
  actor: string;
  /** The operating corporation for network and dividend moves; null in a stock round. */
  corporation: string | null;
  action: Action;
  /** False for the move the client submitted; true for bot and forced moves. */
  automatic: boolean;
  /** Log lines this move wrote (usually one). */
  log: LogEntry[];
  /** For a dividend move: the revenue the corporation earned. 0 otherwise. */
  revenue: number;
  /** The game just after the move. */
  after: FrameState;
}

export interface FrameState {
  phase: Phase;
  roundLabel: string;
  roundNumber: number;
  currentPlayer: string | null;
  currentCorporation: string | null;
  priorityPlayer: string;
  operatingOrder: string[];
  networkActionsTaken: number;
  /** Same fields as PlayerState except name, isBot, difficulty and plan. */
  players: Pick<PlayerState, "id" | "cash" | "worth" | "shares" | "certificates">[];
  /** Full corporation views, as in GameState. */
  corporations: CorporationState[];
  /** Only the tiles this move changed (empty for non-map moves). Merge by hex. */
  tiles: TileState[];
  /** The whole track after the move, under the Death Star rules; absent otherwise. */
  deathStar?: DeathStarState;
  /**
   * Under the facility rules: `planets` holds only the planets this move changed (merge by hex),
   * and there are no `options`. Absent otherwise.
   */
  facilities?: Omit<FacilitiesState, "options">;
}

export interface Seat {
  name: string;
  bot: boolean;
  /** For a bot seat, the difficulty; the server picks a named character to fill it. */
  difficulty?: string;
}

export interface NewGameResponse {
  gameId: string;
  seed: number;
  state: GameState;
}

/** An error response from the API, carrying the server's `detail` message. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  const token = await accessToken();
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
      ...init?.headers,
    },
  });
  if (response.status === 401) {
    // Never replace the token silently: a new account would hide this browser's saved games.
    throw new ApiError(
      401,
      "This browser's saved account was not recognized, so its games cannot be loaded. " +
        `(${await errorDetail(response)})`,
    );
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorDetail(response));
  }
  return response;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await (await send(path, init)).json()) as T;
}

async function errorDetail(response: Response): Promise<string> {
  const fallback = `${response.status} ${response.statusText}`;
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      return typeof detail === "string" ? detail : JSON.stringify(detail);
    }
    return fallback;
  } catch {
    return fallback;
  }
}

/** The tunable numbers behind the rules (see rules_to_json in src/bby18/api/serialize.py). */
export interface Rules {
  corporations: { id: string; name: string; homeworld: string }[];
  networkActionsPerTurn: number;
  chartCost: number;
  upgradeCost: number;
  serviceCost: number;
  nebulaChartSurcharge: number;
  /** Share of non-planet hexes that are asteroid fields (0 to 1). */
  asteroidFraction: number;
  /** Share of non-planet hexes that are nebulae (0 to 1). */
  nebulaFraction: number;
  typedPairValue: number;
  /** Pairs of planet type letters, e.g. ["A", "M"]. */
  typedPairs: [string, string][];
  regionalBonus: number;
  regionalBonusRegions: Region[];
  basicRouteValue: number;
  stockMarket: number[][];
  parColumn: number;
  parPrices: number[];
  payoutStepFractions: number[];
  sharesPerCorporation: number;
  presidentShareSize: number;
  floatThresholdShares: number;
  floatCapitalShares: number;
  startingCash: Record<string, number>;
  maxHoldingShares: number;
  certificateLimit: number;
  totalRounds: number;
  operatingRoundsPerStockRound: number;
  /** Whether the Death Star and fleet rules are in force (always, since 2026-10-26). */
  deathStarRules: boolean;
  /** Their numbers, listed whether or not they are in force. */
  deathStar: DeathStarRules;
  /**
   * Whether the experimental facility rules are in force (they need the Death Star rules). They
   * replace fleets with facilities, priced by `deathStar.fleetTiers` and limited by `fleetLimit`.
   */
  facilityRules: boolean;
  /** Their own numbers, listed whether or not they are in force. */
  facilities: FacilityRules;
}

export interface FacilityRules {
  /** Most facilities one planet may hold. */
  perPlanet: number;
  /** Exits a planet has before any facility is built on it. */
  baseExits: number;
}

export interface DeathStarRules {
  fleetTiers: FleetTierState[];
  fleetLimit: number;
  siteTag: string;
  contractPartnerTags: string[];
  stages: { name: string; value: number; result: StageResult }[];
  cubesPerStage: number;
  empireCubesPerStockRound: number;
  backstopRounds: number;
  /** Region of the first site, then of the second. */
  siteRegions: Region[];
  minHomeworldDistance: number;
}

export function fetchRules(): Promise<Rules> {
  return request<Rules>("/rules");
}

export function fetchBoard(): Promise<Board> {
  return request<Board>("/board");
}

export function createGame(seats: Seat[], seed?: number): Promise<NewGameResponse> {
  const body: { seats: Seat[]; seed?: number } = { seats };
  if (seed !== undefined) body.seed = seed;
  return request<NewGameResponse>("/games", { method: "POST", body: JSON.stringify(body) });
}

export interface GameSummary {
  gameId: string;
  players: Seat[];
  phase: Phase;
  roundLabel: string;
  /** ISO 8601 time of the last move. */
  updatedAt: string;
}

/** The signed-in user's saved games, most recently played first. */
export async function listGames(): Promise<GameSummary[]> {
  return (await request<{ games: GameSummary[] }>("/games")).games;
}

export async function deleteGame(gameId: string): Promise<void> {
  await send(`/games/${encodeURIComponent(gameId)}`, { method: "DELETE" });
}

export function fetchGame(gameId: string): Promise<GameState> {
  return request<GameState>(`/games/${encodeURIComponent(gameId)}`);
}

export function submitAction(gameId: string, action: Action): Promise<GameState> {
  return request<GameState>(`/games/${encodeURIComponent(gameId)}/actions`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

/** Takes back the last submitted action, and any automatic moves that followed it. */
export function undoAction(gameId: string): Promise<GameState> {
  return request<GameState>(`/games/${encodeURIComponent(gameId)}/undo`, { method: "POST" });
}

export function isHexAction(action: Action): action is HexAction {
  return action.type === "chart" || action.type === "upgrade" || action.type === "service";
}
