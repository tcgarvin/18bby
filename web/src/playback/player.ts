/**
 * The playback queue behind `usePlayback`, kept free of React so its timing can be tested with
 * fake timers. It steps through a list of `PlaybackStep`s on a timer and notifies subscribers
 * after every change.
 */

import type { GameState } from "../api";
import type { PlaybackStep } from "./frames";
import type { PlaybackSpeed } from "./timing";
import { stepDuration } from "./timing";

export interface PlaybackSnapshot {
  playing: boolean;
  /** The step showing now; null when idle. */
  current: PlaybackStep | null;
  /** Index of `current` in the steps; 0 when idle. */
  index: number;
  total: number;
  speed: PlaybackSpeed;
  /** How long `current` shows at this speed; 0 when idle. */
  durationMs: number;
  /** The server state the running playback ends at; null when idle. */
  target: GameState | null;
}

export class PlaybackPlayer {
  private steps: PlaybackStep[] = [];
  private index = 0;
  private target: GameState | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private frame: number | null = null;
  private listeners = new Set<() => void>();
  private snapshot: PlaybackSnapshot;
  private speed: PlaybackSpeed;
  private readonly onSpeedChange: (speed: PlaybackSpeed) => void;

  /** `onSpeedChange` hears every speed the viewer picks, e.g. to save it. */
  constructor(speed: PlaybackSpeed, onSpeedChange: (speed: PlaybackSpeed) => void = () => {}) {
    this.speed = speed;
    this.onSpeedChange = onSpeedChange;
    this.snapshot = this.makeSnapshot();
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /** The same object until something changes, as `useSyncExternalStore` requires. */
  getSnapshot = (): PlaybackSnapshot => this.snapshot;

  /**
   * Plays `steps`, ending at `target`. A playback already running jumps to its end first. With
   * no steps, or at instant speed, nothing plays.
   */
  play(steps: PlaybackStep[], target: GameState): void {
    this.stopTimer();
    this.steps = this.speed === "instant" ? [] : steps;
    this.index = 0;
    this.target = this.steps.length > 0 ? target : null;
    this.schedule();
    this.emit();
  }

  /** Jumps to the end of the running playback. */
  skip(): void {
    if (this.steps.length === 0) return;
    this.finish();
    this.emit();
  }

  setSpeed(speed: PlaybackSpeed): void {
    if (speed === this.speed) return;
    this.speed = speed;
    this.onSpeedChange(speed);
    if (speed === "instant") {
      this.finish();
    } else {
      // Restart the current step's timer at the new rate.
      this.schedule();
    }
    this.emit();
  }

  /** Stops the timer, for unmounting. Subscribers unsubscribe themselves. */
  dispose(): void {
    this.stopTimer();
  }

  /**
   * Times the current step from when it is on screen: a step that switches views can take a
   * while to render, and should still show for its full duration.
   */
  private schedule(): void {
    this.stopTimer();
    if (!this.steps[this.index]) return;
    const start = () => {
      this.frame = null;
      this.timer = setTimeout(() => this.advance(), this.currentDuration());
    };
    if (typeof requestAnimationFrame !== "function") {
      start();
      return;
    }
    // Two frames: the first runs before the step's render is painted, the second after.
    this.frame = requestAnimationFrame(() => {
      this.frame = requestAnimationFrame(start);
    });
  }

  /** How long the current step shows at the current speed. */
  currentDuration(): number {
    const step = this.steps[this.index];
    if (!step) return 0;
    const previous = this.index > 0 ? this.steps[this.index - 1].state : step.before;
    return stepDuration(step.kind.kind, this.speed, previous.phase !== step.state.phase);
  }

  private advance(): void {
    this.timer = null;
    if (this.index + 1 < this.steps.length) {
      this.index += 1;
      this.schedule();
    } else {
      this.finish();
    }
    this.emit();
  }

  private finish(): void {
    this.stopTimer();
    this.steps = [];
    this.index = 0;
    this.target = null;
  }

  private stopTimer(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    if (this.frame !== null) cancelAnimationFrame(this.frame);
    this.timer = null;
    this.frame = null;
  }

  private makeSnapshot(): PlaybackSnapshot {
    const current = this.steps[this.index] ?? null;
    return {
      playing: current !== null,
      current,
      index: this.index,
      total: this.steps.length,
      speed: this.speed,
      durationMs: this.currentDuration(),
      target: this.target,
    };
  }

  private emit(): void {
    this.snapshot = this.makeSnapshot();
    for (const listener of this.listeners) listener();
  }
}
