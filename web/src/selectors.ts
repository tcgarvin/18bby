/** Small derived views of GameState used by several components. */

import type { Action, BuyAction, CorporationState, GameState, HexAction, SellAction } from "./api";
import { isHexAction } from "./api";
import { hexKey } from "./hex";

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

/** Price after moving `steps` along the linear track, clamped to its ends. */
export function priceAfter(track: number[], price: number, steps: number): number {
  const index = track.indexOf(price);
  if (index < 0) return price;
  return track[Math.max(0, Math.min(track.length - 1, index + steps))];
}

export interface CorpTradeOptions {
  corpId: string;
  ipoBuys: BuyAction[];
  poolBuy: BuyAction | null;
  sells: SellAction[];
}

/** Legal stock actions grouped by corporation, in corporation order. */
export function tradeOptions(state: GameState): CorpTradeOptions[] {
  return state.corporations
    .map((corp) => {
      const ipoBuys: BuyAction[] = [];
      let poolBuy: BuyAction | null = null;
      const sells: SellAction[] = [];
      for (const action of state.legalActions) {
        if (action.type === "buy" && action.corp === corp.id) {
          if (action.source === "ipo") ipoBuys.push(action);
          else poolBuy = action;
        } else if (action.type === "sell" && action.corp === corp.id) {
          sells.push(action);
        }
      }
      sells.sort((a, b) => a.count - b.count);
      return { corpId: corp.id, ipoBuys, poolBuy, sells };
    })
    .filter((o) => o.ipoBuys.length > 0 || o.poolBuy !== null || o.sells.length > 0);
}
