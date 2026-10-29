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

/** A junction for one corporation, one for two (drawn as trees), and one for three (spokes under a disk). */
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
  it("draws an interchange disk only at the junction busier than two corporations", () => {
    const markup = render();
    expect(markup).not.toMatch(/NaN|Infinity/);
    expect(count(markup, "hexmap__junction")).toBe(1);
  });

  it("draws each corporation's traces on every tile it serves, and on the stub into the planet", () => {
    const markup = render();
    // Trees: a trunk and a branch per corporation (2 + 4). Two-exit tiles: one piece each (2 + 1).
    // The busy junction: a spoke per exit per corporation (9). The stub into Corellia: 2.
    expect(count(markup, "hexmap__trace")).toBe(20);
    expect(count(markup, "hexmap__trace-halo")).toBe(20);
  });

  it("previews an upgrade that makes a junction, without a disk for its one corporation", () => {
    const markup = render({ focusCorp: "A", preview: { type: "upgrade", hex: [-1, 0], exit: "SW", cost: 80 } });
    expect(markup).not.toMatch(/NaN|Infinity/);
    expect(count(markup, "hexmap__preview-trace")).toBe(2);
    expect(count(markup, "hexmap__preview-junction")).toBe(0);
  });
});
