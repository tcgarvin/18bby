import { describe, expect, it } from "vitest";
import { effectsFor } from "./choreography";
import { anchor, flightKeyframes, resolveAnchor } from "./flight";
import { easeOut, tweenValue } from "./useAnimatedNumber";

const rect = (left: number, top: number, width = 20, height = 10) => ({ left, top, width, height });

function fakeElement(r: ReturnType<typeof rect>): Element {
  return { getBoundingClientRect: () => r } as unknown as Element;
}

describe("flightKeyframes", () => {
  it("starts at the source centre and lands on the target centre", () => {
    const frames = flightKeyframes(rect(0, 0), rect(100, 50), 30);
    expect(frames[0].transform).toContain("translate(0px, 0px)");
    expect(frames[frames.length - 1].transform).toContain("translate(100px, 50px)");
    expect(frames[frames.length - 1].opacity).toBe(0);
  });

  it("arcs upward at the midpoint", () => {
    const mid = flightKeyframes(rect(0, 0), rect(100, 0), 30).find((f) => f.offset === 0.5);
    expect(mid?.transform).toContain("translate(50px, -30px)");
  });
});

describe("anchor selectors", () => {
  it("names the data attributes the views carry", () => {
    expect(anchor.ipo("KDY")).toBe('[data-ipo-for="KDY"]');
    expect(anchor.hex([-3, 1])).toBe('[data-hex="-3,1"]');
    expect(anchor.player('odd"id')).toBe('[data-player-id="odd\\"id"]');
  });
});

describe("resolveAnchor", () => {
  const present = fakeElement(rect(5, 5));
  const hidden = fakeElement(rect(0, 0, 0, 0));
  const root = {
    querySelector: (selector: string) =>
      ({ "#present": present, "#hidden": hidden })[selector] ?? null,
  } as Pick<ParentNode, "querySelector">;

  it("finds an anchor by selector", () => {
    expect(resolveAnchor("#present", root)).toBe(present);
  });

  it("treats missing and hidden anchors as absent", () => {
    expect(resolveAnchor("#missing", root)).toBeNull();
    expect(resolveAnchor("#hidden", root)).toBeNull();
  });

  it("falls back along a list", () => {
    expect(resolveAnchor(["#missing", "#hidden", "#present"], root)).toBe(present);
  });
});

describe("effectsFor", () => {
  const color = () => "#123456";

  it("flies a share from the IPO to the buyer and charges the buyer", () => {
    const effects = effectsFor(
      { kind: "buy", player: "P2", corp: "CEC", source: "ipo", shares: 1, cost: 70, treasuryGain: 0, floated: false, newPresident: null, price: { corp: "CEC", before: 70, after: 70 } },
      900,
      color,
    );
    expect(effects[0]).toMatchObject({ effect: "fly", from: ['[data-ipo-for="CEC"]', '[data-corp-id="CEC"]'], to: '[data-player-id="P2"]', label: "CEC" });
    expect(effects[1]).toMatchObject({ effect: "pop", label: "−70" });
    expect(effects).toHaveLength(2);
  });

  it("sends a coin to each paid player on a dividend", () => {
    const effects = effectsFor(
      { kind: "dividend", corp: "KDY", pay: true, revenue: 130, perShare: 13, payouts: { P2: 26, P3: 39 }, treasuryGain: 0, price: { corp: "KDY", before: 120, after: 140 } },
      1600,
      color,
    );
    const coins = effects.filter((e) => e.effect === "fly");
    expect(coins.map((e) => e.effect === "fly" && [e.to, e.label])).toEqual([
      [['[data-cash-for="P2"]', '[data-player-id="P2"]'], "+26"],
      [['[data-cash-for="P3"]', '[data-player-id="P3"]'], "+39"],
    ]);
    expect(effects.some((e) => e.effect === "highlight" && e.target === '[data-market-token="KDY"]')).toBe(true);
  });

  it("pays for a network move from the treasury into the hex", () => {
    const [coin, ring] = effectsFor({ kind: "chart", corp: "KDY", hex: [-3, 1], exits: ["E", "SE"], cost: 60 }, 1200, color);
    expect(coin).toMatchObject({ effect: "fly", to: '[data-hex="-3,1"]', label: "−60", variant: "coin" });
    expect(ring).toMatchObject({ effect: "highlight", target: '[data-hex="-3,1"]', color: "#123456" });
  });

  it("leaves phase banners to the view", () => {
    expect(effectsFor({ kind: "phase", phase: "network", roundLabel: "OR1.1" }, 1100, color)).toEqual([]);
  });
});

describe("tweenValue", () => {
  it("moves from start to target and stops there", () => {
    expect(tweenValue(100, 200, 0, 500)).toBe(100);
    expect(tweenValue(100, 200, 250, 500)).toBe(100 + Math.round(100 * easeOut(0.5)));
    expect(tweenValue(100, 200, 500, 500)).toBe(200);
    expect(tweenValue(100, 200, 900, 500)).toBe(200);
  });

  it("jumps when there is no time to tween", () => {
    expect(tweenValue(100, 200, 0, 0)).toBe(200);
  });
});
