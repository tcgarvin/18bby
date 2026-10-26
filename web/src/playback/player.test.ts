import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { GameState } from "../api";
import { gameState } from "./fixtures";
import type { MoveKind, PlaybackStep } from "./frames";
import { PlaybackPlayer } from "./player";
import { VIEW_SWITCH_MIN_MS, loadSpeed, saveSpeed, stepDuration } from "./timing";

const target = gameState({ roundLabel: "target" });

function step(kind: MoveKind, label: string): PlaybackStep {
  const state: GameState = gameState({ roundLabel: label });
  return { frame: null, kind, caption: label, before: state, state };
}

const buy = step({ kind: "unknown", actor: "P2" }, "buy");
const steps = [
  { ...buy, kind: { kind: "buy", player: "P2", corp: "CEC", source: "ipo", shares: 1, cost: 70, treasuryGain: 0, floated: false, newPresident: null, price: { corp: "CEC", before: 70, after: 70 } } },
  step({ kind: "chart", corp: "CEC", hex: [0, 1], exits: ["E", "W"], cost: 60 }, "chart"),
  step({ kind: "dividend", corp: "CEC", pay: true, revenue: 60, perShare: 6, payouts: {}, treasuryGain: 0, price: { corp: "CEC", before: 70, after: 80 } }, "dividend"),
] satisfies PlaybackStep[];

describe("PlaybackPlayer", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  const showing = (player: PlaybackPlayer) => player.getSnapshot().current?.caption ?? null;

  it("shows each step for its kind's duration at 1x", () => {
    const player = new PlaybackPlayer(1);
    player.play(steps, target);
    expect(showing(player)).toBe("buy");
    vi.advanceTimersByTime(1799);
    expect(showing(player)).toBe("buy");
    vi.advanceTimersByTime(1);
    expect(showing(player)).toBe("chart");
    vi.advanceTimersByTime(2400);
    expect(showing(player)).toBe("dividend");
    expect(player.getSnapshot()).toMatchObject({ playing: true, index: 2, total: 3, target });
    vi.advanceTimersByTime(3200);
    expect(player.getSnapshot()).toMatchObject({ playing: false, current: null, target: null });
  });

  it("holds a step that switches the view for a moment, even at 8x", () => {
    const player = new PlaybackPlayer(8);
    const switching = { ...steps[1], state: gameState({ phase: "network", roundLabel: "chart" }) };
    player.play([steps[0], switching, steps[2]], target);
    vi.advanceTimersByTime(225);
    expect(showing(player)).toBe("chart");
    expect(player.currentDuration()).toBe(VIEW_SWITCH_MIN_MS);
    vi.advanceTimersByTime(VIEW_SWITCH_MIN_MS - 1);
    expect(showing(player)).toBe("chart");
    vi.advanceTimersByTime(1);
    // Back to the stock view: another switch.
    expect(player.currentDuration()).toBe(VIEW_SWITCH_MIN_MS);
  });

  it("runs faster at higher speeds", () => {
    const player = new PlaybackPlayer(4);
    player.play(steps, target);
    vi.advanceTimersByTime(450);
    expect(showing(player)).toBe("chart");
  });

  it("plays nothing at instant speed", () => {
    const player = new PlaybackPlayer("instant");
    player.play(steps, target);
    expect(player.getSnapshot().playing).toBe(false);
  });

  it("skips to the end", () => {
    const player = new PlaybackPlayer(1);
    player.play(steps, target);
    player.skip();
    expect(player.getSnapshot().playing).toBe(false);
    vi.advanceTimersByTime(10_000);
    expect(player.getSnapshot().playing).toBe(false);
  });

  it("finishes the running playback before starting a new one", () => {
    const player = new PlaybackPlayer(1);
    player.play(steps, target);
    vi.advanceTimersByTime(900);
    const next = gameState({ roundLabel: "next" });
    player.play(steps.slice(2), next);
    expect(player.getSnapshot()).toMatchObject({ index: 0, total: 1, target: next });
    expect(showing(player)).toBe("dividend");
  });

  it("applies a new speed to the step showing", () => {
    const saved: unknown[] = [];
    const player = new PlaybackPlayer(1, (s) => saved.push(s));
    player.play(steps, target);
    vi.advanceTimersByTime(500);
    player.setSpeed(2);
    vi.advanceTimersByTime(899);
    expect(showing(player)).toBe("buy");
    vi.advanceTimersByTime(1);
    expect(showing(player)).toBe("chart");
    player.setSpeed("instant");
    expect(player.getSnapshot()).toMatchObject({ playing: false, speed: "instant" });
    expect(saved).toEqual([2, "instant"]);
  });

  it("notifies subscribers and keeps the snapshot stable between changes", () => {
    const player = new PlaybackPlayer(1);
    const listener = vi.fn();
    const unsubscribe = player.subscribe(listener);
    const idle = player.getSnapshot();
    expect(player.getSnapshot()).toBe(idle);
    player.play(steps, target);
    vi.advanceTimersByTime(1800);
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
    player.skip();
    expect(listener).toHaveBeenCalledTimes(2);
  });
});

describe("timing", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("scales base durations by speed", () => {
    expect(stepDuration("dividend", 1)).toBe(3200);
    expect(stepDuration("dividend", 2)).toBe(1600);
    expect(stepDuration("chart", 8)).toBe(300);
    expect(stepDuration("buy", "instant")).toBe(0);
    expect(stepDuration("no_action", 8, true)).toBe(VIEW_SWITCH_MIN_MS);
    expect(stepDuration("dividend", 1, true)).toBe(3200);
  });

  it("defaults to 1x, or instant for reduced motion, without storage", () => {
    expect(loadSpeed(false)).toBe(1);
    expect(loadSpeed(true)).toBe("instant");
  });

  it("round-trips the saved speed and ignores junk", () => {
    const store = new Map<string, string>();
    vi.stubGlobal("window", {
      localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) },
    });
    saveSpeed(4);
    expect(loadSpeed(false)).toBe(4);
    saveSpeed("instant");
    expect(loadSpeed(false)).toBe("instant");
    store.set("bby18.playbackSpeed", "11");
    expect(loadSpeed(false)).toBe(1);
  });

  it("survives storage that throws", () => {
    vi.stubGlobal("window", {
      localStorage: {
        getItem: () => {
          throw new Error("blocked");
        },
        setItem: () => {
          throw new Error("blocked");
        },
      },
    });
    expect(() => saveSpeed(2)).not.toThrow();
    expect(loadSpeed(true)).toBe("instant");
  });
});
