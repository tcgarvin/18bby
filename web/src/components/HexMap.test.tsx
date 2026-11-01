import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Axial, Board, TileState } from "../api";
import { neighbor } from "../hex";
import { corporation } from "../playback/fixtures";
import { HexMap, MapViewToggle } from "./HexMap";

function hexesWithin(radius: number): Axial[] {
  const hexes: Axial[] = [];
  for (let q = -radius; q <= radius; q++) {
    for (let r = Math.max(-radius, -q - radius); r <= Math.min(radius, -q + radius); r++) hexes.push([q, r]);
  }
  return hexes;
}

const BOARD: Board = {
  radius: 3,
  hexes: hexesWithin(3),
  planets: [{ name: "Corellia", hex: neighbor([1, 0], "NE"), region: "Core", tags: ["I"] }],
};

/** Junctions where corporations fork, carry straight on, or stop short of a tile they do not serve. */
const TILES: TileState[] = [
  { hex: [0, 0], exits: ["E", "W", "SE"], service: ["A", "B"] },
  { hex: [1, 0], exits: ["W", "NE"], service: ["A", "B"] },
  { hex: [-1, 0], exits: ["E", "NW"], service: ["A"] },
  { hex: [0, 1], exits: ["NW", "SW", "E"], service: ["A", "B", "C"] },
  { hex: [-2, 1], exits: ["E", "W", "NE"], service: ["C"] },
];

function render(overrides: Partial<Parameters<typeof HexMap>[0]> = {}): string {
  return renderToStaticMarkup(
    <HexMap
      board={BOARD}
      tiles={TILES}
      terrain={new Map()}
      nebulaChartSurcharge={20}
      corporations={["A", "B", "C"].map((id) => corporation(id, { status: "floated" }))}
      focusCorp={null}
      actionableHexes={new Set()}
      selectedHex={null}
      preview={null}
      changedHexes={new Map()}
      onHexClick={() => undefined}
      {...overrides}
    />,
  );
}

function count(markup: string, className: string): number {
  return markup.match(new RegExp(`class="${className}[ "]`, "g"))?.length ?? 0;
}

describe("HexMap lanes", () => {
  it("draws each corporation's traces where it carries on, and on the stub into the planet", () => {
    const markup = render();
    expect(markup).not.toMatch(/NaN|Infinity/);
    // At 0,0 A forks three ways (2) and B, which does not serve the tile to the west, bends from
    // east to south-east (1). Two-exit tiles: one each (2 + 1). At 0,1 A and B fork into open
    // space and from the north-west (2 + 2), and C bends between the open ends (1). C forks at
    // -2,1 (2). The stub into Corellia: 2.
    expect(count(markup, "hexmap__trace")).toBe(15);
    expect(count(markup, "hexmap__trace-halo")).toBe(15);
  });

  it("previews an upgrade that makes a junction as a fork", () => {
    const markup = render({ focusCorp: "A", preview: { type: "upgrade", hex: [-1, 0], exit: "SW", cost: 80 } });
    expect(markup).not.toMatch(/NaN|Infinity/);
    expect(count(markup, "hexmap__preview-trace")).toBe(2);
  });
});

const planets = [
  { name: "Kessel", hex: [-2, 2] as Axial, region: "Outer Rim" as const, tags: ["R"] },
  { name: "Sullust", hex: [0, 2] as Axial, region: "Mid Rim" as const, tags: ["I"] },
  { name: "Kuat", hex: [2, -1] as Axial, region: "Core" as const, tags: ["S"] },
];
const links = [
  { a: "Kessel", b: "Sullust", value: 30, typed: true, contract: false },
  { a: "Sullust", b: "Kuat", value: 30, typed: true, contract: false },
];

/** The map with corporation A focused and its two links, under the chain rules or the pair rules. */
function focused(chains: boolean, overrides: Partial<Parameters<typeof HexMap>[0]> = {}): string {
  const corp = corporation("A", {
    status: "floated",
    revenue: {
      total: 80,
      pairs: links,
      chains: chains ? [{ stops: ["Kessel", "Sullust", "Kuat"], links, regional: 20, value: 80 }] : [],
    },
  });
  return render({ board: { ...BOARD, planets }, tiles: [], corporations: [corp], focusCorp: "A", ...overrides });
}

/** One opening tag of the toggle's button, with its attributes. */
function toggleButton(markup: string, view: string): string {
  const tag = markup.match(new RegExp(`<button[^>]*data-map-view="${view}"[^>]*>`));
  if (tag === null) throw new Error(`no ${view} button`);
  return tag[0];
}

function attribute(markup: string, pattern: RegExp): string {
  const match = markup.match(pattern);
  if (match === null) throw new Error(`nothing matches ${pattern}`);
  return match[1];
}

/** A hex's outline as the map draws it, which the scrim's path repeats for every tinted hex. */
function cellOutline(markup: string, key: string): string {
  return attribute(markup, new RegExp(`data-hex="${key}" d="([^"]+)"`));
}

function rememberRoutes(): void {
  vi.stubGlobal("window", { localStorage: { getItem: () => "routes", setItem: () => undefined } });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HexMap revenue arcs", () => {
  it("points each chain link the way its cargo travels and tells the whole chain", () => {
    const markup = focused(true, { startOnRoutes: true });
    expect(markup).not.toMatch(/NaN|Infinity/);
    expect(count(markup, "hexmap__pair")).toBe(2);
    expect(count(markup, "hexmap__pair-arrow")).toBe(2);
    expect(markup).toContain("<title>Kessel → Sullust → Kuat · 30 + 30 + 20 regional</title>");
  });

  it("draws plain pairs without arrows under the pair rules", () => {
    const markup = focused(false, { startOnRoutes: true });
    expect(count(markup, "hexmap__pair")).toBe(2);
    expect(count(markup, "hexmap__pair-arrow")).toBe(0);
  });
});

describe("HexMap lane edge", () => {
  it.each([
    ["with the toggle", {}],
    ["without it, as in the thumbnail", { viewToggle: false }],
  ])("softens the casing with an SVG filter over the whole view, %s", (_name, overrides) => {
    const markup = render(overrides);
    const filterId = attribute(markup, /<g class="hexmap__casings" filter="url\(#([^)]+)\)"/);
    const filter = attribute(markup, new RegExp(`(<filter id="${filterId}"[^>]*>)`));
    expect(filter).toContain('filterUnits="userSpaceOnUse"');
    expect(filter).toContain('color-interpolation-filters="sRGB"');
    expect(filter).toContain(`width="${attribute(markup, /viewBox="\S+ \S+ (\S+) \S+"/)}"`);
    expect(markup).toContain('<feGaussianBlur stdDeviation="1.3">');
  });
});

describe("HexMap zoomed to a network", () => {
  it("masks and softens lanes over the whole board, since a wide panel shows past the viewBox", () => {
    const whole = render();
    const zoomed = render({ fitHexes: [[0, 0]] });
    const regions = (markup: string): string[] =>
      [...markup.matchAll(/<(?:mask|filter) [^>]*?x="([^"]+)" y="([^"]+)" width="([^"]+)" height="([^"]+)"/g)].map((match) => match.slice(1).join(" "));
    expect(regions(zoomed)).toHaveLength(2);
    expect(regions(zoomed)).toEqual(regions(whole));
  });
});

describe("HexMap Regular and Routes views", () => {
  it("draws no links, tint or route classes in the Regular view", () => {
    const markup = focused(true);
    expect(markup).not.toContain("hexmap--routes");
    expect(markup).not.toContain("hexmap__scrim");
    expect(markup).not.toContain("hexmap__pair");
    expect(markup).not.toContain("--on-route");
    expect(markup).not.toContain("--off-route");
  });

  it("draws links with their halos, the tint and route classes in the Routes view", () => {
    const markup = focused(true, { startOnRoutes: true });
    expect(markup).toContain("hexmap--routes");
    expect(count(markup, "hexmap__scrim")).toBe(1);
    expect(count(markup, "hexmap__pair")).toBe(2);
    expect(count(markup, "hexmap__pair-halo")).toBe(2);
    expect(markup).toContain("hexmap__planet--on-route");
  });

  it("steps back a planet the links do not touch", () => {
    const corp = corporation("A", { status: "floated", revenue: { total: 30, pairs: links.slice(0, 1), chains: [] } });
    const markup = render({ board: { ...BOARD, planets }, tiles: [], corporations: [corp], focusCorp: "A", startOnRoutes: true });
    expect(markup).toMatch(/hexmap__planet--off-route"[^>]*><title>Kuat/);
    expect(markup).toMatch(/hexmap__planet--on-route"[^>]*><title>Kessel/);
  });

  it("keeps build targets out of the tint", () => {
    const markup = focused(true, { startOnRoutes: true, actionableHexes: new Set(["1,1"]) });
    const scrim = attribute(markup, /<path d="([^"]+)" class="hexmap__scrim"/);
    expect(scrim).not.toContain(cellOutline(markup, "1,1"));
    expect(scrim).toContain(cellOutline(markup, "0,0"));
  });

  it("shows a remembered Routes choice", () => {
    rememberRoutes();
    expect(focused(true)).toContain("hexmap--routes");
  });

  it("tells a typed link from a basic one and a contract", () => {
    const mixed = [
      { a: "Kessel", b: "Sullust", value: 30, typed: true, contract: false },
      { a: "Sullust", b: "Kuat", value: 10, typed: false, contract: false },
      { a: "Kessel", b: "Kuat", value: 50, typed: true, contract: true },
    ];
    const corp = corporation("A", { status: "floated", revenue: { total: 90, pairs: mixed, chains: [] } });
    const markup = render({ board: { ...BOARD, planets }, tiles: [], corporations: [corp], focusCorp: "A", startOnRoutes: true });
    expect(count(markup, "hexmap__pair")).toBe(3);
    expect(markup).toContain('class="hexmap__pair hexmap__pair--basic"');
    expect(markup).toContain('class="hexmap__pair hexmap__pair--contract"');
  });
});

describe("HexMap view toggle", () => {
  it("labels its buttons and marks the view showing", () => {
    const regular = focused(true);
    expect(regular).toMatch(/<div class="hexmap-view" role="group" aria-label="Map view">/);
    expect(regular).toMatch(/data-map-view="regular"[^>]*>Regular<\/button>/);
    expect(regular).toMatch(/data-map-view="routes"[^>]*>Routes<\/button>/);
    expect(toggleButton(regular, "regular")).toContain('aria-pressed="true"');
    expect(toggleButton(regular, "routes")).toContain('aria-pressed="false"');
    expect(toggleButton(regular, "routes")).not.toContain("disabled");
    const routes = focused(true, { startOnRoutes: true });
    expect(toggleButton(routes, "regular")).toContain('aria-pressed="false"');
    expect(toggleButton(routes, "routes")).toContain('aria-pressed="true"');
  });

  it("has neither toggle nor frame when viewToggle is false, and stays Regular", () => {
    rememberRoutes();
    const markup = focused(true, { viewToggle: false });
    expect(markup).not.toContain("data-map-view");
    expect(markup).not.toContain("hexmap-frame");
    expect(markup).not.toContain("hexmap--routes");
    expect(markup).not.toContain("hexmap__pair");
  });

  it("disables Routes with no focus, and renders Regular even if Routes is remembered", () => {
    rememberRoutes();
    const markup = render();
    const routes = toggleButton(markup, "routes");
    expect(routes).toContain("disabled");
    expect(routes).toContain('title="Pick a corporation to see its routes"');
    expect(toggleButton(markup, "regular")).toContain('aria-pressed="true"');
    expect(markup).not.toContain("hexmap--routes");
  });

  it("disables Routes for a focused corporation with no links, and renders Regular", () => {
    rememberRoutes();
    const corp = corporation("A", { status: "floated", revenue: { total: 0, pairs: [], chains: [] } });
    const markup = render({ board: { ...BOARD, planets }, tiles: [], corporations: [corp], focusCorp: "A" });
    const routes = toggleButton(markup, "routes");
    expect(routes).toContain("disabled");
    expect(routes).toContain('title="A has no routes yet"');
    expect(markup).not.toContain("hexmap--routes");
    expect(markup).not.toContain("hexmap__scrim");
  });

  /** Clicks the toggle's button for `view`, as it stands with the given state, and returns what was chosen. */
  function press(view: "regular" | "routes", routesOn: boolean): string[] {
    const chosen: string[] = [];
    const toggle = MapViewToggle({ routesOn, routesBlocked: null, onChoose: (next) => chosen.push(next) });
    const [regular, routes] = (toggle.props as { children: { props: { onClick: () => void } }[] }).children;
    (view === "regular" ? regular : routes).props.onClick();
    return chosen;
  }

  it("chooses the view that is not showing", () => {
    expect(press("routes", false)).toEqual(["routes"]);
    expect(press("regular", true)).toEqual(["regular"]);
  });

  it("does not count pressing the view already showing as a choice, so a remembered Routes survives", () => {
    expect(press("regular", false)).toEqual([]);
    expect(press("routes", true)).toEqual([]);
  });
});
