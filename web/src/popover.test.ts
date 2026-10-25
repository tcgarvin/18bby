import { describe, expect, it } from "vitest";
import { placePopover } from "./popover";

const viewport = { width: 1366, height: 768 };
const size = { width: 300, height: 120 };

describe("placePopover", () => {
  it("opens below the trigger, aligned with it", () => {
    expect(placePopover({ left: 200, top: 100, bottom: 116 }, size, viewport)).toEqual({ left: 192, top: 122 });
  });

  it("slides left to stay inside the right edge", () => {
    expect(placePopover({ left: 1350, top: 100, bottom: 116 }, size, viewport).left).toBe(1366 - 8 - 300);
  });

  it("keeps clear of the left edge", () => {
    expect(placePopover({ left: 2, top: 100, bottom: 116 }, size, viewport).left).toBe(8);
  });

  it("flips above the trigger when there is no room below", () => {
    expect(placePopover({ left: 200, top: 700, bottom: 716 }, size, viewport).top).toBe(700 - 6 - 120);
  });

  it("stays inside a window too short for either side", () => {
    // Neither below (76 + 6 + 120 > 152) nor above (60 - 6 - 120 < 8) fits: pin to the bottom edge.
    expect(placePopover({ left: 200, top: 60, bottom: 76 }, size, { width: 1366, height: 160 }).top).toBe(160 - 8 - 120);
  });
});
