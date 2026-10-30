import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Axial, Board, TileState } from "../api";
import { neighbor } from "../hex";
import { corporation } from "../playback/fixtures";
import { HexMap } from "./HexMap";

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

describe("HexMap revenue arcs", () => {
  const planets = [
    { name: "Kessel", hex: [-2, 2] as Axial, region: "Outer Rim" as const, tags: ["R"] },
    { name: "Sullust", hex: [0, 2] as Axial, region: "Mid Rim" as const, tags: ["I"] },
    { name: "Kuat", hex: [2, -1] as Axial, region: "Core" as const, tags: ["S"] },
  ];
  const links = [
    { a: "Kessel", b: "Sullust", value: 30, typed: true, contract: false },
    { a: "Sullust", b: "Kuat", value: 30, typed: true, contract: false },
  ];

  function focused(chains: boolean): string {
    const corp = corporation("A", {
      status: "floated",
      revenue: {
        total: 80,
        pairs: links,
        chains: chains ? [{ stops: ["Kessel", "Sullust", "Kuat"], links, regional: 20, value: 80 }] : [],
      },
    });
    return render({ board: { ...BOARD, planets }, tiles: [], corporations: [corp], focusCorp: "A" });
  }

  it("points each chain link the way its cargo travels and tells the whole chain", () => {
    const markup = focused(true);
    expect(markup).not.toMatch(/NaN|Infinity/);
    expect(count(markup, "hexmap__pair")).toBe(2);
    expect(count(markup, "hexmap__pair-arrow")).toBe(2);
    expect(markup).toContain("<title>Kessel → Sullust → Kuat · 30 + 30 + 20 regional</title>");
  });

  it("draws plain pairs without arrows under the pair rules", () => {
    const markup = focused(false);
    expect(count(markup, "hexmap__pair")).toBe(2);
    expect(count(markup, "hexmap__pair-arrow")).toBe(0);
  });
});
