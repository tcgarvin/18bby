import { describe, expect, it } from "vitest";
import type { GameState } from "./api";
import {
  availableViews,
  browseBanner,
  followSelection,
  initialSelection,
  liveView,
  shownView,
  viewForKey,
} from "./gameView";

const FACILITIES = {} as NonNullable<GameState["facilities"]>;

describe("liveView", () => {
  it("puts the stock round on Shares and every operating step on the Map", () => {
    expect(liveView("stock")).toBe("shares");
    expect(liveView("network")).toBe("map");
    expect(liveView("fleet")).toBe("map");
    expect(liveView("dividend")).toBe("map");
  });

  it("shows the results at game over", () => {
    expect(liveView("game_over")).toBe("results");
  });
});

describe("availableViews", () => {
  it("offers Shares and Map, and Results only once the game is over", () => {
    expect(availableViews("network")).toEqual(["shares", "map"]);
    expect(availableViews("game_over")).toEqual(["shares", "map", "results"]);
  });
});

describe("followSelection", () => {
  const browsingShares = { view: "shares" as const, phase: "network" as const, playing: false };

  it("keeps a choice while the phase stays and no replay starts", () => {
    expect(followSelection(browsingShares, "network", false)).toBe(browsingShares);
  });

  it("snaps back to the live view when the phase changes", () => {
    const next = followSelection(browsingShares, "dividend", false);
    expect(next.view).toBeNull();
    expect(shownView(next)).toBe("map");
  });

  it("snaps back to the live view when a replay starts", () => {
    const next = followSelection(browsingShares, "network", true);
    expect(next).toEqual({ view: null, phase: "network", playing: true });
  });

  it("keeps a choice made during a replay when the replay ends", () => {
    const duringReplay = { view: "shares" as const, phase: "network" as const, playing: true };
    expect(followSelection(duringReplay, "network", false)).toEqual({ ...duringReplay, playing: false });
  });
});

describe("shownView", () => {
  it("follows the live view until the player chooses", () => {
    expect(shownView(initialSelection("stock", false))).toBe("shares");
    expect(shownView({ view: "map", phase: "stock", playing: false })).toBe("map");
  });

  it("ignores a choice the phase does not offer", () => {
    expect(shownView({ view: "results", phase: "network", playing: false })).toBe("map");
  });
});

describe("viewForKey", () => {
  it("flips between Shares and Map with V", () => {
    expect(viewForKey("v", "shares", "network")).toBe("map");
    expect(viewForKey("v", "map", "network")).toBe("shares");
  });

  it("steps through Results too at game over", () => {
    expect(viewForKey("v", "results", "game_over")).toBe("shares");
    expect(viewForKey("v", "map", "game_over")).toBe("results");
  });

  it("picks a view directly with M and S, and K as an alias for S", () => {
    expect(viewForKey("m", "shares", "stock")).toBe("map");
    expect(viewForKey("s", "map", "stock")).toBe("shares");
    expect(viewForKey("k", "map", "dividend")).toBe("shares");
  });

  it("ignores other keys", () => {
    expect(viewForKey("p", "shares", "stock")).toBeNull();
    expect(viewForKey("l", "map", "network")).toBeNull();
  });
});

describe("browseBanner", () => {
  it("has no banner on the live view", () => {
    expect(browseBanner({ phase: "stock" }, "shares")).toBeNull();
    expect(browseBanner({ phase: "network" }, "map")).toBeNull();
    expect(browseBanner({ phase: "game_over" }, "results")).toBeNull();
  });

  it("says the map is read-only during the stock round", () => {
    expect(browseBanner({ phase: "stock" }, "map")).toEqual({
      text: "Stock round in progress · Map is read-only.",
      back: "Back to Shares",
    });
  });

  it("names the operating step when browsing Shares", () => {
    expect(browseBanner({ phase: "network" }, "shares")?.text).toBe(
      "Operating round in progress (building lanes) · Shares are read-only.",
    );
    expect(browseBanner({ phase: "fleet", facilities: FACILITIES }, "shares")?.text).toContain("building facilities");
    expect(browseBanner({ phase: "fleet" }, "shares")?.text).toContain("buying fleets");
    expect(browseBanner({ phase: "dividend" }, "shares")?.back).toBe("Back to Map");
  });

  it("leads back to the results at game over", () => {
    expect(browseBanner({ phase: "game_over" }, "map")).toEqual({
      text: "The game is over · Map is read-only.",
      back: "Back to results",
    });
  });
});
