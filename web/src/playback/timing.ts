/** How long each playback step shows, and the viewer's chosen playback speed. */

import type { MoveKindName } from "./frames";

/** A multiplier on the base durations, or "instant" to show only the final state. */
export type PlaybackSpeed = 1 | 2 | 4 | "instant";

export const PLAYBACK_SPEEDS: PlaybackSpeed[] = [1, 2, 4, "instant"];

/** Milliseconds each step shows at 1×. Network and dividend moves have more to watch. */
export const BASE_DURATION_MS: Record<MoveKindName, number> = {
  buy: 900,
  sell: 900,
  pass: 600,
  chart: 1200,
  upgrade: 1200,
  service: 1200,
  no_action: 600,
  dividend: 1600,
  phase: 1100,
  unknown: 900,
};

/**
 * The least time a step shows when it switches the view (say, from the map to the dividend
 * cards), at any speed, so fast playback does not strobe between layouts.
 */
export const VIEW_SWITCH_MIN_MS = 550;

/** How long a step shows; `switchesView` when its phase differs from the step before. */
export function stepDuration(kind: MoveKindName, speed: PlaybackSpeed, switchesView = false): number {
  if (speed === "instant") return 0;
  const duration = BASE_DURATION_MS[kind] / speed;
  return switchesView ? Math.max(duration, VIEW_SWITCH_MIN_MS) : duration;
}

const STORAGE_KEY = "bby18.playbackSpeed";

function isSpeed(value: unknown): value is PlaybackSpeed {
  return PLAYBACK_SPEEDS.some((speed) => String(speed) === value);
}

/** True when the viewer has asked the system for less motion. */
export function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    // No window (tests, server rendering) or no matchMedia: assume motion is fine.
    return false;
  }
}

/**
 * The speed saved in this browser, or else instant for viewers who prefer reduced motion and
 * 1× for everyone else.
 */
export function loadSpeed(reducedMotion: boolean = prefersReducedMotion()): PlaybackSpeed {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored !== null && isSpeed(stored)) return stored === "instant" ? "instant" : (Number(stored) as PlaybackSpeed);
  } catch {
    // Storage blocked or unavailable: fall through to the default.
  }
  return reducedMotion ? "instant" : 1;
}

export function saveSpeed(speed: PlaybackSpeed): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, String(speed));
  } catch {
    // Not saving the preference is harmless; it applies for this page load only.
  }
}
