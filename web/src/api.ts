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

export type Phase = "stock" | "network" | "dividend" | "game_over";

export type CorpStatus = "unstarted" | "parred" | "floated";

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

export type Action =
  | PassAction
  | BuyAction
  | SellAction
  | ChartAction
  | UpgradeAction
  | ServiceAction
  | NoNetworkAction
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
  reachablePlanets: string[];
  revenue: { total: number; pairs: RevenuePair[] };
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
  log: LogEntry[];
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
