/**
 * Derived views of the facility rules (the state's optional `facilities` block): planet exits
 * and facilities on the map, a corporation's facility-step options, and what moves changed.
 * Everything here reads what the server sent; the rules themselves stay on the server.
 */

import type {
  Axial,
  BuildFacilityAction,
  CorporationState,
  DeathStarState,
  DirectionName,
  FacilitiesState,
  FacilityOption,
  FinishFleetsAction,
  GameState,
  HexAction,
  PlanetFacilities,
  SupplyItem,
} from "./api";
import { EMPIRE } from "./api";
import { DIRECTIONS, hexKey, neighbor, sameHex } from "./hex";

/** What the supply sells in this game: fleets, or facilities under the facility rules. */
export function supplyItem(deathStar: DeathStarState | undefined): SupplyItem {
  return deathStar?.fleets.item ?? "fleet";
}

/** "fleet", "fleets", "facility" or "facilities" for `count` of them. */
export function itemWord(item: SupplyItem, count: number): string {
  if (item === "facility") return count === 1 ? "facility" : "facilities";
  return count === 1 ? "fleet" : "fleets";
}

/** "1 fleet", "3 facilities". */
export function itemCount(item: SupplyItem, count: number): string {
  return `${count} ${itemWord(item, count)}`;
}

/** Exit-limited planets by `hexKey`. Planets not listed (and the Death Star site) are open hubs. */
export function planetsByKey(facilities: Pick<FacilitiesState, "planets"> | undefined): Map<string, PlanetFacilities> {
  return new Map((facilities?.planets ?? []).map((planet) => [hexKey(planet.hex), planet] as const));
}

/**
 * Whether a lane facing the planet at `planetKey` from its `side` connects into it: always for an
 * open hub (not in `planets`), and for an exit-limited planet only through a claimed exit.
 */
export function laneConnects(planets: Map<string, PlanetFacilities>, planetKey: string, side: DirectionName): boolean {
  const planet = planets.get(planetKey);
  return planet === undefined || planet.claimed.includes(side);
}

/** `base` with each planet in `changed` replacing the one on its hex (a move frame lists only those it changed). */
export function mergePlanets(base: PlanetFacilities[], changed: PlanetFacilities[]): PlanetFacilities[] {
  if (changed.length === 0) return base;
  const byKey = new Map(changed.map((planet) => [hexKey(planet.hex), planet] as const));
  const merged = base.map((planet) => byKey.get(hexKey(planet.hex)) ?? planet);
  const known = new Set(base.map((planet) => hexKey(planet.hex)));
  return [...merged, ...changed.filter((planet) => !known.has(hexKey(planet.hex)))];
}

/**
 * The facility state after a move frame: its changed planets merged into `base`, with the frame's
 * seizure targets. Nothing is buildable while a replay shows, so there are no options.
 */
export function mergeFacilities(
  base: FacilitiesState | undefined,
  frame: Omit<FacilitiesState, "options"> | undefined,
): FacilitiesState | undefined {
  if (!frame) return base;
  return {
    perPlanet: frame.perPlanet,
    planets: mergePlanets(base?.planets ?? [], frame.planets),
    seizureTargets: frame.seizureTargets,
    options: [],
  };
}

/** Whether two build actions are the same move: same planet, same exit, same price. */
export function sameBuild(a: BuildFacilityAction, b: BuildFacilityAction): boolean {
  return sameHex(a.planet, b.planet) && a.exit === b.exit && a.cost === b.cost;
}

/** One legal build, with the server's preview of what it does when it sent one. */
export interface BuildChoice {
  action: BuildFacilityAction;
  preview: FacilityOption | null;
}

/** The legal facility builds, by planet `hexKey`, each planet's in the server's order. */
export function buildsByPlanet(state: Pick<GameState, "legalActions" | "facilities">): Map<string, BuildChoice[]> {
  const options = state.facilities?.options ?? [];
  const byPlanet = new Map<string, BuildChoice[]>();
  for (const action of state.legalActions) {
    if (action.type !== "build_facility") continue;
    const preview = options.find((option) => sameBuild(option.action, action)) ?? null;
    const key = hexKey(action.planet);
    byPlanet.set(key, [...(byPlanet.get(key) ?? []), { action, preview }]);
  }
  return byPlanet;
}

/** What a build adds to this turn's revenue: never negative, 0 without a preview. */
export function buildGain(choice: BuildChoice, corp: CorporationState): number {
  return choice.preview ? Math.max(0, choice.preview.revenue - corp.revenue.total) : 0;
}

/** The most any of `choices` (one planet's builds) adds to this turn's revenue. */
export function bestGain(choices: BuildChoice[], corp: CorporationState): number {
  return Math.max(0, ...choices.map((choice) => buildGain(choice, corp)));
}

/** The hex of the lane a build gives its new exit to, or null when it leaves the exit unclaimed. */
export function laneHex(action: BuildFacilityAction): Axial | null {
  return action.exit ? neighbor(action.planet, action.exit) : null;
}

export interface FacilityChoice {
  /** Legal builds by planet `hexKey`. */
  builds: Map<string, BuildChoice[]>;
  finish: FinishFleetsAction | null;
  /** It owns no facility yet, so it must build one before finishing. */
  mandatory: boolean;
  atLimit: boolean;
}

/** The operating corporation's facility-step options, from the server's legal actions. */
export function facilityChoice(state: GameState, corp: CorporationState): FacilityChoice {
  const finish = state.legalActions.find((action): action is FinishFleetsAction => action.type === "finish_fleets") ?? null;
  const limit = state.deathStar?.fleets.limit ?? 0;
  return { builds: buildsByPlanet(state), finish, mandatory: corp.fleets === 0, atLimit: corp.fleets >= limit };
}

/** The planet whose facility the next seizure would take from `corpId`, or null if it owns none. */
export function seizureTarget(state: Pick<GameState, "facilities">, corpId: string): PlanetFacilities | null {
  const target = state.facilities?.seizureTargets.find((t) => t.corp === corpId);
  if (!target) return null;
  return state.facilities?.planets.find((planet) => sameHex(planet.hex, target.hex)) ?? null;
}

/** The planets where `corpId` owns facilities, one entry per facility, oldest first. */
export function facilitiesOf(facilities: Pick<FacilitiesState, "planets"> | undefined, corpId: string): PlanetFacilities[] {
  return (facilities?.planets ?? []).flatMap((planet) => planet.facilities.filter((f) => f.owner === corpId).map(() => planet));
}

/** A facility the Empire took over in a move. */
export interface SeizedFacility {
  corp: string;
  planet: string;
  hex: Axial;
}

/**
 * Facilities that turned Imperial between `before` and `after` (a frame may list only the planets
 * it changed), by comparing owners of the same build number.
 */
export function seizedFacilities(
  before: Pick<FacilitiesState, "planets"> | undefined,
  after: Pick<FacilitiesState, "planets"> | undefined,
): SeizedFacility[] {
  if (!before || !after) return [];
  const owners = new Map(before.planets.flatMap((planet) => planet.facilities.map((f) => [f.build, f.owner] as const)));
  return after.planets.flatMap((planet) =>
    planet.facilities.flatMap((f) => {
      const was = owners.get(f.build);
      return f.owner === EMPIRE && was !== undefined && was !== EMPIRE ? [{ corp: was, planet: planet.name, hex: planet.hex }] : [];
    }),
  );
}

/**
 * Planets whose facilities changed between two states, each mapped to the corporations that gained
 * one there (none for a seizure), for outlining others' moves on the map.
 */
export function changedFacilityHexes(
  before: Pick<FacilitiesState, "planets"> | undefined,
  after: Pick<FacilitiesState, "planets"> | undefined,
): Map<string, string[]> {
  const changed = new Map<string, string[]>();
  if (!after) return changed;
  const previous = planetsByKey(before);
  for (const planet of after.planets) {
    const old = previous.get(hexKey(planet.hex))?.facilities ?? [];
    const builds = new Set(old.map((f) => `${f.build}:${f.owner}`));
    const fresh = planet.facilities.filter((f) => !builds.has(`${f.build}:${f.owner}`));
    if (fresh.length === 0) continue;
    const known = new Set(old.map((f) => f.build));
    changed.set(
      hexKey(planet.hex),
      fresh.filter((f) => !known.has(f.build) && f.owner !== EMPIRE).map((f) => f.owner),
    );
  }
  return changed;
}

/** "Corellia: 2 exits (SE claimed, 1 open); CEC, Empire facilities; 0 slots free; a lane dangles on its W side". */
export function planetExitsText(planet: PlanetFacilities): string {
  const exits = [
    ...(planet.claimed.length > 0 ? [`${planet.claimed.join(", ")} claimed`] : []),
    ...(planet.unclaimed > 0 ? [`${planet.unclaimed} open`] : []),
  ];
  const parts = [`${planet.exits} ${planet.exits === 1 ? "exit" : "exits"}${exits.length > 0 ? ` (${exits.join(", ")})` : ""}`];
  if (planet.facilities.length > 0) {
    parts.push(`facilities: ${planet.facilities.map((f) => f.owner).join(", ")}`);
  }
  parts.push(`${planet.freeSlots} ${planet.freeSlots === 1 ? "facility slot" : "facility slots"} free`);
  if (planet.dangling.length > 0) {
    const sides = planet.dangling.join(", ");
    parts.push(`${planet.dangling.length === 1 ? "a lane dangles" : "lanes dangle"} on its ${sides} ${planet.dangling.length === 1 ? "side" : "sides"}`);
  }
  return parts.join("; ");
}

/** What a new lane does at an exit-limited planet it faces: claims one of its open exits, or dangles. */
export interface LaneArrival {
  planet: string;
  claims: boolean;
}

/**
 * For a chart or upgrade, each exit-limited planet a new exit faces and whether it claims an open
 * exit there (first come, first served) or dangles. Service adds no exit, so it claims nothing.
 */
export function laneArrivals(action: HexAction, facilities: Pick<FacilitiesState, "planets"> | undefined): LaneArrival[] {
  if (!facilities || action.type === "service") return [];
  const planets = planetsByKey(facilities);
  const exits = action.type === "chart" ? action.exits : [action.exit];
  return exits.flatMap((exit) => {
    const planet = planets.get(hexKey(neighbor(action.hex, exit)));
    const side = DIRECTIONS[(DIRECTIONS.indexOf(exit) + 3) % 6];
    if (!planet) return [];
    return [{ planet: planet.name, claims: planet.claimed.includes(side) || planet.unclaimed > 0 }];
  });
}

/** "CEC", "CEC and KDY", "CEC, CSC and KDY". */
function andList(items: string[]): string {
  return items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/** Whose lane a build connects: "your lane", "KDY's lane", "a lane you share with KDY", "a lane CSC and KDY serve". */
export function laneOwners(lane: string[], corpId: string): string {
  const others = lane.filter((id) => id !== corpId);
  if (lane.length === 0) return "a lane nobody serves";
  if (others.length === 0) return "your lane";
  if (others.length < lane.length) return `a lane you share with ${andList(others)}`;
  return others.length === 1 ? `${others[0]}'s lane` : `a lane ${andList(others)} serve`;
}
