/**
 * Derived views of the Death Star track, its construction sites and the fleet supply (the
 * experimental Death Star rules). Everything here reads the server's `deathStar` block; the rules
 * themselves stay on the server.
 */

import type {
  Axial,
  BuyFleetAction,
  CorporationState,
  DeathStarSite,
  DeathStarStage,
  DeathStarState,
  FinishFleetsAction,
  FleetTierState,
  GameState,
  Planet,
  StageResult,
} from "./api";

/** The site under construction as a planet (a hub with every exit), or null once it has launched. */
export function sitePlanet(deathStar: DeathStarState | undefined): Planet | null {
  const active = deathStar?.sites.find((site) => site.status === "active");
  if (!deathStar || !active) return null;
  return { name: deathStar.siteName, hex: active.hex, region: active.region, tags: [deathStar.siteTag] };
}

/** Hexes of the sites with `status`. */
export function siteHexes(deathStar: DeathStarState | undefined, status: DeathStarSite["status"]): Axial[] {
  return (deathStar?.sites ?? []).filter((site) => site.status === status).map((site) => site.hex);
}

/** The next future site, where the station moves when its move stage fills; null if none is left. */
export function nextSite(deathStar: DeathStarState): DeathStarSite | null {
  return deathStar.sites.find((site) => site.status === "reserved") ?? null;
}

/** Cubes on stage `index`: 0 to `cubesPerStage`. Extra cubes carry over to later stages. */
export function stageCubes(deathStar: DeathStarState, index: number): number {
  return Math.max(0, Math.min(deathStar.cubesPerStage, deathStar.cubes - index * deathStar.cubesPerStage));
}

export interface StageProgress {
  /** The stage being built, or null once every stage has resolved (the station launched). */
  stage: DeathStarStage | null;
  index: number;
  /** Cubes on it so far. */
  cubes: number;
  /** Cubes still needed to fill it; 0 when it has filled and its result waits for the round's end. */
  toFill: number;
}

export function stageProgress(deathStar: DeathStarState): StageProgress {
  const index = deathStar.stage;
  const stage = deathStar.stages[index] ?? null;
  const cubes = stage ? stageCubes(deathStar, index) : 0;
  return { stage, index, cubes, toFill: stage ? deathStar.cubesPerStage - cubes : 0 };
}

/** Filled stages whose results apply at the end of the current round, in order. */
export function pendingStages(deathStar: DeathStarState): DeathStarStage[] {
  return deathStar.stages.filter((stage) => stage.filled && !stage.resolved);
}

/** What a stage result does, in a few words. */
export function resultText(result: StageResult, deathStar?: DeathStarState): string {
  switch (result) {
    case "seizure":
      return "Seizure: every corporation with a fleet loses one";
    case "move": {
      const next = deathStar ? nextSite(deathStar) : null;
      return next ? `The site moves to the ${next.region}` : "The site moves";
    }
    case "completion":
      return "The station launches and the game ends after this round";
  }
}

/** A short label for a stage result, for the track. */
export function resultLabel(result: StageResult): string {
  return result === "seizure" ? "Seizure" : result === "move" ? "Site moves" : "Launch";
}

/** The round the game ends after, and why: the station launched, or the backstop. */
export function gameEnd(deathStar: DeathStarState): { round: number; reason: "launch" | "backstop" } {
  return { round: deathStar.finalRound, reason: deathStar.launched ? "launch" : "backstop" };
}

/** "4 left at 60, then 90" for the supply; "160 each, unlimited" in the last tier. */
export function supplyText(deathStar: DeathStarState): string {
  const { tiers, tier, price, remainingInTier } = deathStar.fleets;
  if (remainingInTier === "unlimited") return `${price} each, unlimited`;
  const next: FleetTierState | undefined = tiers[tier + 1];
  return `${remainingInTier} left at ${price}${next ? `, then ${next.price}` : ""}`;
}

export interface FleetChoice {
  buy: BuyFleetAction | null;
  finish: FinishFleetsAction | null;
  /** Revenue this turn's matching gains from one more fleet. */
  adds: number;
  /** It owns no fleet yet, so it must buy one before finishing. */
  mandatory: boolean;
  atLimit: boolean;
}

/** The operating corporation's fleet-step options, from the server's legal actions. */
export function fleetChoice(state: GameState, corp: CorporationState): FleetChoice {
  let buy: BuyFleetAction | null = null;
  let finish: FinishFleetsAction | null = null;
  for (const action of state.legalActions) {
    if (action.type === "buy_fleet") buy = action;
    else if (action.type === "finish_fleets") finish = action;
  }
  const adds = corp.fleetRevenue ? Math.max(0, corp.fleetRevenue.withNextFleet - corp.revenue.total) : 0;
  const limit = state.deathStar?.fleets.limit ?? 0;
  return { buy, finish, adds, mandatory: corp.fleets === 0, atLimit: corp.fleets >= limit };
}

export interface SeizureRisk {
  stage: DeathStarStage;
  /** Cubes until it fills; 0 when it has filled and the seizure comes at the end of this round. */
  cubesToGo: number;
  /** Whether the treasury could buy a replacement fleet at today's price. */
  covered: boolean;
  price: number;
}

/**
 * The seizure a corporation with `fleets` and `treasury` should plan for: the stage being built
 * ends in a seizure and would leave it with no fleet. At its next fleet step it must then buy one,
 * and if it cannot pay it goes bankrupt. Null when the stage being built is not a seizure or the
 * corporation keeps a fleet through it.
 */
export function seizureRisk(deathStar: DeathStarState, fleets: number, treasury: number): SeizureRisk | null {
  const stage = deathStar.stages[deathStar.stage];
  if (!stage || stage.result !== "seizure" || fleets !== 1) return null;
  const cubesToGo = Math.max(0, (deathStar.stage + 1) * deathStar.cubesPerStage - deathStar.cubes);
  const price = deathStar.fleets.price;
  return { stage, cubesToGo, covered: treasury >= price, price };
}

export interface PairUsage {
  /** Pairs the matching runs now (at most one per fleet). */
  run: number;
  /** Pairs the network could run with no fleet limit. */
  available: number;
  fleets: number;
}

/** How many of a network's pairs its fleets run; null without the Death Star rules. */
export function pairUsage(corp: CorporationState): PairUsage | null {
  if (!corp.fleetRevenue) return null;
  return { run: corp.revenue.pairs.length, available: corp.fleetRevenue.uncappedPairs, fleets: corp.fleets };
}

/** "3 of 5 pairs run · 3 fleets", or "2 pairs run · 3 fleets" when every pair is run. */
export function pairUsageText(usage: PairUsage): string {
  const fleets = `${usage.fleets} ${usage.fleets === 1 ? "fleet" : "fleets"}`;
  const pairs = usage.available === 1 ? "pair" : "pairs";
  if (usage.available > usage.run) return `${usage.run} of ${usage.available} ${pairs} run · ${fleets}`;
  return `${usage.run} ${usage.run === 1 ? "pair" : "pairs"} run · ${fleets}`;
}
