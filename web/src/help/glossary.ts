import type { Rules } from "../api";

/**
 * Every term the game teaches, in one place. The "?" popovers, the coach tips and the rules page
 * glossary all read from here so a rule is only ever explained one way. Summaries are functions of
 * the live rules so quoted numbers cannot drift from the engine's config.
 */
export interface GlossaryEntry {
  term: string;
  /** One to three sentences for a popover. */
  summary: (rules: Rules) => string;
  /** Id of the rules-page section that explains it in full. */
  section: SectionId;
  /** Part of the experimental Death Star rules: listed only when they are in force. */
  deathStar?: boolean;
}

export type SectionId =
  | "goal"
  | "round-structure"
  | "map"
  | "terrain"
  | "corporations"
  | "stock-round"
  | "operating-turn"
  | "revenue"
  | "fleets"
  | "death-star"
  | "stock-market"
  | "scoring"
  | "verify"
  | "glossary";

export const SECTION_IDS: SectionId[] = [
  "goal",
  "round-structure",
  "map",
  "terrain",
  "corporations",
  "stock-round",
  "operating-turn",
  "revenue",
  "fleets",
  "death-star",
  "stock-market",
  "scoring",
  "verify",
  "glossary",
];

const sharePercent = (r: Rules): number => 100 / r.sharesPerCorporation;

/** How many rounds the game runs at most: the backstop under the Death Star rules. */
export const roundCount = (r: Rules): number => (r.deathStarRules ? r.deathStar.backstopRounds : r.totalRounds);

const tierPrices = (r: Rules): string =>
  r.deathStar.fleetTiers
    .map((t) => (t.count === "unlimited" ? `then any number at ${t.price}` : `${t.count} at ${t.price}`))
    .join(", ");

const stageOf = (r: Rules, result: string): string =>
  r.deathStar.stages
    .filter((s) => s.result === result)
    .map((s) => s.name)
    .join(" and ");

export const GLOSSARY = {
  share: {
    term: "Share",
    summary: (r) =>
      `Each corporation is split into ${r.sharesPerCorporation} shares, ${sharePercent(r)}% each. Owning shares earns you a cut of the corporation's dividends and counts toward your final score at the current share price.`,
    section: "corporations",
  },
  certificate: {
    term: "Certificate limit",
    summary: (r) =>
      `A player may hold at most ${r.certificateLimit} certificates, roughly one per share. A president's 20% certificate counts as one, not two.`,
    section: "stock-round",
  },
  holdingLimit: {
    term: "Holding limit",
    summary: (r) =>
      `You may own at most ${r.maxHoldingShares} shares (${r.maxHoldingShares * sharePercent(r)}%) of any one corporation.`,
    section: "stock-round",
  },
  par: {
    term: "Par price",
    summary: (r) =>
      `The price the president picks when starting a corporation: one of ${r.parPrices.join(", ")}. It sets the starting share price, what IPO shares cost, and how much capital the corporation receives when it floats.`,
    section: "corporations",
  },
  ipo: {
    term: "IPO",
    summary: () =>
      "Shares not yet sold to anyone. They are bought at par from the corporation itself. Unsold IPO shares pay no dividends to anybody.",
    section: "corporations",
  },
  pool: {
    term: "Pool",
    summary: (r) =>
      `Shares players have sold back. Anyone can buy them at the current share price. The pool never holds more than ${r.sharesPerCorporation / 2} shares of one corporation, and its shares pay no dividends.`,
    section: "stock-round",
  },
  president: {
    term: "President",
    summary: (r) =>
      `The player holding the largest stake (at least ${r.presidentShareSize * sharePercent(r)}%). The president decides everything the corporation does on its operating turn. The job passes automatically to whoever owns more.`,
    section: "corporations",
  },
  float: {
    term: "Floating",
    summary: (r) =>
      `Once ${r.floatThresholdShares} of the ${r.sharesPerCorporation} shares are sold the corporation floats: the bank gives it ${r.floatCapitalShares} × par as its treasury and it starts operating. Until then it cannot lay track or earn.`,
    section: "corporations",
  },
  treasury: {
    term: "Treasury",
    summary: () =>
      "The corporation's own money, separate from the players'. It pays for charting, upgrading and service. Withheld revenue goes here; paid-out revenue goes to shareholders.",
    section: "corporations",
  },
  sharePrice: {
    term: "Share price",
    summary: () =>
      "What one share is worth right now. It sets the price to buy from the pool, what you receive when you sell, your final score, and the order corporations operate in.",
    section: "stock-market",
  },
  priority: {
    term: "Priority deal",
    summary: () =>
      "The player who acts first in the next stock round. It passes to the player after whoever last bought or sold a share.",
    section: "stock-round",
  },
  stockRound: {
    term: "Stock round",
    summary: () =>
      "Players take turns buying and selling shares. It ends when every player passes in a row. Nothing on the map happens during a stock round.",
    section: "stock-round",
  },
  operatingRound: {
    term: "Operating round",
    summary: () =>
      "Each floated corporation takes a turn, highest share price first: build track, collect revenue, then pay or withhold.",
    section: "operating-turn",
  },
  operatingOrder: {
    term: "Operating order",
    summary: () =>
      "Floated corporations operate from highest share price to lowest. A tie goes to whichever floated first.",
    section: "operating-turn",
  },
  networkAction: {
    term: "Network action",
    summary: (r) =>
      `On its turn a corporation may take up to ${r.networkActionsPerTurn} actions on the map: chart a new hex, upgrade a tile, or extend service. Each costs the amount shown and comes out of the treasury.`,
    section: "operating-turn",
  },
  chart: {
    term: "Chart",
    summary: (r) =>
      `Survey an empty hex next to your network by choosing two hyperspace lanes (exits) for it. Costs ${r.chartCost}, or ${r.chartCost + r.nebulaChartSurcharge} in a nebula. Your corporation gets service there automatically.`,
    section: "operating-turn",
  },
  upgrade: {
    term: "Upgrade",
    summary: (r) =>
      `Add a third lane to a charted hex where you already have service. The original two lanes stay. Costs ${r.upgradeCost}. More lanes means more places your network can branch. A tile in a nebula can never be upgraded.`,
    section: "operating-turn",
  },
  service: {
    term: "Service",
    summary: (r) =>
      `Pay ${r.serviceCost} to extend your corporation onto a hex someone else already charted, next to your network. A corporation can only pass through hexes where it has service.`,
    section: "operating-turn",
  },
  lanes: {
    term: "Exits (lanes)",
    summary: () =>
      "Each charted hex has hyperspace lanes leaving through some of its six sides. Two neighbouring hexes connect only if each has a lane facing the other. Planets have all six.",
    section: "map",
  },
  terrain: {
    term: "Terrain",
    summary: (r) =>
      `Asteroid fields are impassable: they cannot be charted and no lane may face one. Nebulae cost ${r.nebulaChartSurcharge} extra to chart and their tiles never gain a third lane.`,
    section: "terrain",
  },
  hub: {
    term: "Planet hub",
    summary: () =>
      "Planets are open hubs: they have every exit, never need charting, and any corporation can pass through them freely once it reaches them.",
    section: "map",
  },
  reachable: {
    term: "Reachable planets",
    summary: () =>
      "The planets a corporation can trace to from its homeworld along connected hexes where it has service. Only these can earn revenue.",
    section: "map",
  },
  homeworld: {
    term: "Homeworld",
    summary: () => "Where a corporation's network starts. It is always reachable by that corporation.",
    section: "map",
  },
  region: {
    term: "Region",
    summary: (r) =>
      `The galaxy is split into Core, Mid Rim and Outer Rim. A trade pair spanning ${r.regionalBonusRegions.join(" and ")} earns a +${r.regionalBonus} bonus.`,
    section: "map",
  },
  planetTypes: {
    term: "Planet types",
    summary: () =>
      "A Agriculture, R Resources, I Industry, S Shipyard, M Market. Some planets carry two types and may count as whichever scores better.",
    section: "revenue",
  },
  revenue: {
    term: "Revenue",
    summary: () =>
      "Money a corporation earns each operating turn from pairs of planets in its network. The engine picks the best set of pairs for you.",
    section: "revenue",
  },
  typedPair: {
    term: "Trade pair",
    summary: (r) =>
      `Two planets whose types fit a supply chain (${r.typedPairs.map(([a, b]) => `${a}↔${b}`).join(", ")}) earn ${r.typedPairValue}. A planet is used in at most one pair per turn.`,
    section: "revenue",
  },
  basicRoute: {
    term: "Basic route",
    summary: (r) =>
      `Any two leftover reachable planets that do not form a trade pair still earn ${r.basicRouteValue} together. No bonuses apply.`,
    section: "revenue",
  },
  regionalBonus: {
    term: "Regional bonus",
    summary: (r) =>
      `A trade pair with one end in the ${r.regionalBonusRegions[0]} and the other in the ${r.regionalBonusRegions[1]} earns +${r.regionalBonus}. Basic routes never get it.`,
    section: "revenue",
  },
  dividend: {
    term: "Pay dividends",
    summary: (r) =>
      `Split the revenue into ${r.sharesPerCorporation} equal per-share amounts (rounded down). Each share players hold pays its owner. IPO and pool shares pay nobody. The share price moves right.`,
    section: "operating-turn",
  },
  withhold: {
    term: "Withhold",
    summary: () =>
      "Keep all the revenue in the corporation's treasury to fund more track. Nobody is paid, and the share price moves left one column.",
    section: "operating-turn",
  },
  marketMovement: {
    term: "How the price moves",
    summary: () =>
      "Right when a corporation pays a big dividend, left when it withholds, down when its shares are sold, up when it is sold out at the end of a stock round.",
    section: "stock-market",
  },
  soldOut: {
    term: "Sold out",
    summary: () =>
      "At the end of a stock round, a started corporation with no shares left in the IPO or the pool moves up one row.",
    section: "stock-market",
  },
  netWorth: {
    term: "Worth",
    summary: () =>
      "Your cash plus every share you own at its current share price. The player with the highest worth when the game ends wins.",
    section: "scoring",
  },
  round: {
    term: "Round",
    summary: (r) =>
      r.deathStarRules
        ? `The game lasts up to ${roundCount(r)} rounds, and ends sooner once the Death Star launches. Each is one stock round followed by ${r.operatingRoundsPerStockRound} operating rounds.`
        : `The game lasts ${r.totalRounds} rounds. Each is one stock round followed by ${r.operatingRoundsPerStockRound} operating rounds.`,
    section: "round-structure",
  },
  fleet: {
    term: "Fleet",
    summary: (r) =>
      `One fleet runs one revenue pair: a corporation earns from at most as many pairs as it owns fleets. It may own up to ${r.deathStar.fleetLimit}, and must own at least one after its fleet step. Fleets cannot be sold.`,
    section: "fleets",
    deathStar: true,
  },
  fleetSupply: {
    term: "Fleet supply",
    summary: (r) =>
      `All corporations buy fleets from one shared supply: ${tierPrices(r)}. The price rises when a tier sells out, so every fleet bought makes the next one dearer for everybody.`,
    section: "fleets",
    deathStar: true,
  },
  bankruptcy: {
    term: "Bankruptcy",
    summary: () =>
      "A corporation that reaches its fleet step with no fleet and too little in its treasury to buy one closes for good. Its shares are worth nothing to anyone, its money goes to the bank, and its tiles stay for others.",
    section: "fleets",
    deathStar: true,
  },
  deathStar: {
    term: "Death Star track",
    summary: (r) =>
      `The Empire is building a battle station. Each contract pair a corporation runs adds a cube, and the Empire adds ${r.deathStar.empireCubesPerStockRound} after every stock round. Every ${r.deathStar.cubesPerStage} cubes fill a stage, and each stage does something when it fills.`,
    section: "death-star",
    deathStar: true,
  },
  contract: {
    term: "Contract pair",
    summary: (r) =>
      `The construction site (${r.deathStar.siteTag}) paired with a planet tagged ${r.deathStar.contractPartnerTags.join(", ")}. It scores the current stage's contract value (${r.deathStar.stages.map((s) => s.value).join(", ")}), never the regional bonus, and adds a cube to the track. The best matching may pick it whether you like it or not.`,
    section: "death-star",
    deathStar: true,
  },
  seizure: {
    term: "Seizure",
    summary: (r) =>
      `When the ${stageOf(r, "seizure")} stage fills, at the end of that round the Empire takes one fleet from every corporation that has one. A corporation left with none must buy one at its next turn or go bankrupt.`,
    section: "death-star",
    deathStar: true,
  },
  siteMove: {
    term: "Site move",
    summary: (r) =>
      `When the ${stageOf(r, "move")} stage fills, the construction site moves to its reserved second hex in the ${r.deathStar.siteRegions[1]}. The old hex becomes empty space and networks through it are cut there.`,
    section: "death-star",
    deathStar: true,
  },
  launch: {
    term: "Launch",
    summary: (r) =>
      `When the ${stageOf(r, "completion")} stage fills, the station launches: the site leaves the board, the current round's operating rounds finish, and the game ends (the Battle of Yavin). Otherwise it ends after round ${r.deathStar.backstopRounds}.`,
    section: "death-star",
    deathStar: true,
  },
  undo: {
    term: "Undo",
    summary: () =>
      "Takes back your last move and anything the bots played automatically afterwards. Handy for learning.",
    section: "verify",
  },
} satisfies Record<string, GlossaryEntry>;

export type GlossaryId = keyof typeof GLOSSARY;

/** Where the rules page lives; opens in a new tab so a game in progress is never lost. */
export function rulesUrl(section?: SectionId): string {
  return section ? `/?rules=${section}` : "/?rules";
}
