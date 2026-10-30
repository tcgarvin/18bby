/** Small derived views of GameState used by several components. */

import type {
  Action,
  BuyAction,
  BuyBlock,
  CorporationState,
  GameState,
  HexAction,
  LogEntry,
  SellAction,
  TerrainHex,
  TerrainKind,
} from "./api";
import { isHexAction } from "./api";
import { demandedCorporations } from "./chains";
import { corporationColor } from "./colors";
import { hexKey } from "./hex";

/** Corporation ids in table order, for `corporationColor`. */
export function corpIds(state: Pick<GameState, "corporations">): string[] {
  return state.corporations.map((c) => c.id);
}

/** A corporation's color, looked up against the state's own corporation list. */
export function corpColor(state: Pick<GameState, "corporations">, corpId: string): string {
  return corporationColor(corpId, corpIds(state));
}

export type StepStage = "done" | "current" | "upcoming";

export interface PhaseStep {
  label: string;
  stage: StepStage;
}

/**
 * The rounds of the current game round, e.g. SR4 › OR4.1 › OR4.2, with the one in play lit.
 * `roundLabel` is the server's label: "SR<n>", "OR<n>.<i>", "end" or "setup".
 */
export function phaseSteps(roundLabel: string, operatingRoundsPerStockRound: number, totalRounds: number): PhaseStep[] {
  const stock = /^SR(\d+)$/.exec(roundLabel);
  const operating = /^OR(\d+)\.(\d+)$/.exec(roundLabel);
  const round = stock ? Number(stock[1]) : operating ? Number(operating[1]) : totalRounds;
  const position = stock ? 0 : operating ? Number(operating[2]) : operatingRoundsPerStockRound + 1;
  const labels = [`SR${round}`];
  for (let i = 1; i <= operatingRoundsPerStockRound; i += 1) labels.push(`OR${round}.${i}`);
  return labels.map((label, i) => ({
    label,
    stage: i < position ? "done" : i === position ? "current" : "upcoming",
  }));
}

export interface QueueEntry {
  corpId: string;
  stage: StepStage;
  /** What the corporation did in this operating round, from the log (empty until it operates). */
  log: LogEntry[];
}

/**
 * The operating round's corporations in the order they operate, with who is done. The server's
 * `operatingOrder` is the round's fixed queue: those before the operating corporation are done,
 * those after it are still to come.
 */
export function operatingQueue(state: GameState): QueueEntry[] {
  if (state.phase === "surrender") return surrenderQueue(state);
  if (state.phase !== "network" && state.phase !== "fleet" && state.phase !== "dividend") return [];
  const thisRound = state.log.filter((entry) => entry.round === state.roundLabel);
  const currentAt = state.currentCorporation === null ? -1 : state.operatingOrder.indexOf(state.currentCorporation);
  return state.operatingOrder.map((corpId, i) => {
    const stage: StepStage = currentAt < 0 || i > currentAt ? "upcoming" : i === currentAt ? "current" : "done";
    const log = stage === "upcoming" ? [] : thisRound.filter((entry) => entry.actor === corpId);
    return { corpId, stage, log };
  });
}

/**
 * A seizure under the chain rules: the corporations it asked for a facility, in the order they
 * choose, with who has chosen. A corporation's log is the Empire's line taking its facility.
 */
function surrenderQueue(state: GameState): QueueEntry[] {
  const order = demandedCorporations(state);
  const thisRound = state.log.filter((entry) => entry.round === state.roundLabel && entry.actor === "Empire");
  const currentAt = state.currentCorporation === null ? -1 : order.indexOf(state.currentCorporation);
  return order.map((corpId, i) => {
    const stage: StepStage = currentAt < 0 || i > currentAt ? "upcoming" : i === currentAt ? "current" : "done";
    const log = stage === "done" ? thisRound.filter((entry) => entry.text.startsWith(`takes over ${corpId}'s facility`)).slice(-1) : [];
    return { corpId, stage, log };
  });
}

export interface Payout {
  playerId: string;
  shares: number;
  amount: number;
}

export interface DividendSplit {
  perShare: number;
  /** Every player, including those who hold none and receive nothing. */
  payouts: Payout[];
  /** Revenue that stays with the bank: unheld (IPO and pool) shares and the rounding remainder. */
  bankKeeps: number;
}

/**
 * Who receives what if the corporation pays `total`. Mirrors `Game.settle_revenue`: each
 * player-held share gets `total // sharesPerCorporation`; IPO and pool shares earn nothing.
 */
export function dividendSplit(state: GameState, corp: CorporationState, total: number): DividendSplit {
  const perShare = Math.floor(total / state.config.sharesPerCorporation);
  const payouts = state.players.map((p) => {
    const shares = p.shares[corp.id] ?? 0;
    return { playerId: p.id, shares, amount: shares * perShare };
  });
  const paid = payouts.reduce((sum, p) => sum + p.amount, 0);
  return { perShare, payouts, bankKeeps: total - paid };
}

/**
 * The market cell showing `price` nearest to `from`, preferring the same row. Used only to
 * point at where a dividend preview price sits on the grid; the server decides the move.
 */
export function nearestCellWithPrice(
  market: number[][],
  from: [number, number],
  price: number,
): [number, number] | null {
  let best: [number, number] | null = null;
  let bestScore = Infinity;
  market.forEach((row, r) =>
    row.forEach((value, c) => {
      if (value !== price) return;
      const score = Math.abs(r - from[0]) * 100 + Math.abs(c - from[1]);
      if (score < bestScore) {
        best = [r, c];
        bestScore = score;
      }
    }),
  );
  return best;
}

export function playerName(state: GameState, playerId: string | null): string {
  if (!playerId) return "—";
  return state.players.find((p) => p.id === playerId)?.name ?? playerId;
}

export function findCorporation(state: GameState, corpId: string | null): CorporationState | null {
  if (!corpId) return null;
  return state.corporations.find((c) => c.id === corpId) ?? null;
}

export function hexActionsByKey(actions: Action[]): Map<string, HexAction[]> {
  const byKey = new Map<string, HexAction[]>();
  for (const action of actions) {
    if (!isHexAction(action)) continue;
    const key = hexKey(action.hex);
    byKey.set(key, [...(byKey.get(key) ?? []), action]);
  }
  return byKey;
}

/** Terrain keyed by `hexKey`; hexes that are plain space are absent. */
export function terrainByKey(terrain: TerrainHex[]): Map<string, TerrainKind> {
  return new Map(terrain.map((t) => [hexKey(t.hex), t.kind] as const));
}

export interface CorpTradeOptions {
  corpId: string;
  ipoBuys: BuyAction[];
  poolBuy: BuyAction | null;
  sells: SellAction[];
}

/** The legal stock actions for one corporation (all empty when it has none). */
export function tradeOptionsFor(state: GameState, corpId: string): CorpTradeOptions {
  const ipoBuys: BuyAction[] = [];
  let poolBuy: BuyAction | null = null;
  const sells: SellAction[] = [];
  for (const action of state.legalActions) {
    if (action.type === "buy" && action.corp === corpId) {
      if (action.source === "ipo") ipoBuys.push(action);
      else poolBuy = action;
    } else if (action.type === "sell" && action.corp === corpId) {
      sells.push(action);
    }
  }
  sells.sort((a, b) => a.count - b.count);
  return { corpId, ipoBuys, poolBuy, sells };
}

/** A short line saying why the current player cannot buy `corp`, for its stock-round card. */
export function buyBlockText(state: GameState, corp: CorporationState, block: BuyBlock): string {
  switch (block.reason) {
    case "closed":
      return "Closed";
    case "none_for_sale":
      return "Sold out";
    case "sold_this_round":
      return `You sold ${corp.id} this round, so can't buy it back`;
    case "certificate_limit":
      return `At your certificate limit (${state.config.certificateLimit})`;
    case "holding_limit": {
      const percent = (state.config.maxHoldingShares * 100) / state.config.sharesPerCorporation;
      return `At the ${percent}% holding limit`;
    }
    case "cannot_afford":
      return corp.status === "unstarted" ? `Starting needs ${block.cost} cash` : `A share needs ${block.cost} cash`;
  }
}

/** The label for whoever made a log entry: a corporation id, or a player's name. */
export function actorLabel(state: GameState, actor: string): string {
  return state.corporations.some((c) => c.id === actor) ? actor : playerName(state, actor);
}
