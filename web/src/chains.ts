/**
 * Derived views of supply chains (the chain rules): a corporation's revenue told as the cargo
 * runs ("Kessel → Sullust → Corellia → Death Star · 30 + 30 + 60 + 20 regional"), and the
 * choice a seizure puts to a corporation. Under the pair rules each pair reads as a chain of two
 * stops, so one display serves both.
 */

import type { CorporationState, GameState, Revenue, RevenueChain, RevenuePair, SurrenderOption } from "./api";

/** The chains behind `revenue`: the server's chains, or under the pair rules each pair as a two-stop chain. */
export function revenueChains(revenue: Revenue): RevenueChain[] {
  if (revenue.chains.length > 0) return revenue.chains;
  // Under the pair rules a pair's value already includes its regional bonus.
  return revenue.pairs.map((pair) => ({ stops: [pair.a, pair.b], links: [pair], regional: 0, value: pair.value }));
}

/** "Kessel → Sullust → Corellia → Death Star". */
export function chainPath(chain: RevenueChain): string {
  return chain.stops.join(" → ");
}

/** What a chain earns, link by link: "30 + 30 + 60 + 20 regional", or just "30" for one link. */
export function chainSum(chain: RevenueChain): string {
  const parts = chain.links.map((link) => String(link.value));
  if (chain.regional > 0) parts.push(`${chain.regional} regional`);
  return parts.join(" + ");
}

/** The cargo story: "Kessel → Sullust → Corellia → Death Star · 30 + 30 + 60 + 20 regional". */
export function chainStory(chain: RevenueChain): string {
  return `${chainPath(chain)} · ${chainSum(chain)}`;
}

export type LinkKind = "contract" | "typed" | "basic";

/** How a link (or pair) scores: a Death Star contract, a typed link, or a basic route. */
export function linkKind(link: RevenuePair): LinkKind {
  return link.contract ? "contract" : link.typed ? "typed" : "basic";
}

/** How a chain scores as a whole: a contract if it delivers to the site, typed if every link is, else basic. */
export function chainKind(chain: RevenueChain): LinkKind {
  if (chain.links.some((link) => link.contract)) return "contract";
  return chain.links.every((link) => link.typed) ? "typed" : "basic";
}

/** Stops where a chain drops one cargo and picks up the next: every stop but its two ends. */
export function middleStops(chain: RevenueChain): string[] {
  return chain.stops.slice(1, -1);
}

/** The chain (or, under the pair rules, the pair) that `link` belongs to in `revenue`, if any. */
export function chainOfLink(revenue: Revenue, link: RevenuePair): RevenueChain | null {
  return revenueChains(revenue).find((chain) => chain.links.some((l) => l.a === link.a && l.b === link.b)) ?? null;
}

/** One facility a corporation may give up at a seizure, and what it keeps earning after. */
export interface SurrenderChoice extends SurrenderOption {
  /** The revenue it loses by giving this one up: now less after (0 or more). */
  loss: number;
}

/**
 * The surrender the game waits on: the corporation choosing, its options (the cheapest loss
 * first, then by planet name), and the corporations still to choose after it. Null outside a
 * surrender phase.
 */
export function surrenderChoice(
  state: Pick<GameState, "phase" | "facilities" | "corporations" | "currentCorporation">,
): { corp: CorporationState; options: SurrenderChoice[]; waiting: string[] } | null {
  if (state.phase !== "surrender" || !state.facilities) return null;
  const corp = state.corporations.find((c) => c.id === state.currentCorporation);
  if (!corp) return null;
  // A replayed surrender shows the move's corporation while the options are already the next one's.
  const choosing = state.facilities.surrenderQueue[0] === corp.id;
  const options = (choosing ? state.facilities.surrenderOptions : [])
    .map((option) => ({ ...option, loss: Math.max(0, corp.revenue.total - option.revenue) }))
    .sort((a, b) => a.loss - b.loss || a.name.localeCompare(b.name));
  return { corp, options, waiting: state.facilities.surrenderQueue.filter((id) => id !== corp.id) };
}

/**
 * The corporations a seizure under the chain rules asked for a facility, in the order they
 * choose, from the Empire's latest "demands a facility from CEC, KDY" log line; falls back to the
 * corporations still to choose when that line has scrolled out of the log.
 */
export function demandedCorporations(state: Pick<GameState, "log" | "facilities">): string[] {
  const queue = state.facilities?.surrenderQueue ?? [];
  for (let i = state.log.length - 1; i >= 0; i -= 1) {
    const entry = state.log[i];
    const match = /^demands a facility from (.+)$/.exec(entry.text);
    if (entry.actor === "Empire" && match) {
      const named = match[1].split(", ");
      // The line belongs to this seizure only if everyone still to choose is on it.
      if (queue.every((id) => named.includes(id))) return named;
      break;
    }
  }
  return queue;
}

/** "CEC", "CEC and KDY", "CEC, KDY and KTG". */
export function listText(items: string[]): string {
  return items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}
