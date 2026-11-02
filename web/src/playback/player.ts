/**
 * The playback queue behind `usePlayback`, kept free of React so its timing can be tested with
 * fake timers. It steps through a list of `PlaybackStep`s on a timer and notifies subscribers
 * after every change.
 */

import type { GameState } from "../api";
import type { PlaybackStep } from "./frames";
import type { PlaybackSpeed } from "./timing";
import { leadDuration, stepDuration } from "./timing";

export interface PlaybackSnapshot {
  playing: boolean;
  /** True while a running playback is held; `current` stays on screen. */
  paused: boolean;
  /** The step showing now; null when idle. */
  current: PlaybackStep | null;
  /** Index of `current` in the steps; 0 when idle. */
  index: number;
  total: number;
  speed: PlaybackSpeed;
  /** How long `current`'s effects have at this speed; 0 when idle. */
  durationMs: number;
  /** How long `current` waits for the camera before its effects start; 0 when it doesn't. */
  leadMs: number;
  /** The server state the running playback ends at; null when idle. */
  target: GameState | null;
}

export class PlaybackPlayer {
  private steps: PlaybackStep[] = [];
  private leads: number[] = [];
  private index = 0;
  private target: GameState | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private frame: number | null = null;
  private paused = false;
  /** When the running timer started, and how long it was set for. */
  private timerStart = 0;
  private timerLength = 0;
  /** What is left of the current step while paused. */
  private remaining = 0;
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
   * no steps, or at instant speed, nothing plays. `leads` gives each step's wait for the camera
   * at 1×, added before its effects; absent entries wait for nothing.
   */
  play(steps: PlaybackStep[], target: GameState, leads: number[] = []): void {
    this.stopTimer();
    this.paused = false;
    this.steps = this.speed === "instant" ? [] : steps;
    this.leads = leads;
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

  /** Holds the running playback on its current step. */
  pause(): void {
    if (this.steps.length === 0 || this.paused) return;
    const elapsed = this.timer === null ? 0 : Date.now() - this.timerStart;
    this.remaining = Math.max(0, (this.timer === null ? this.currentDuration() : this.timerLength) - elapsed);
    this.stopTimer();
    this.paused = true;
    this.emit();
  }

  /** Carries on with what was left of the step that was paused. */
  resume(): void {
    if (!this.paused) return;
    this.paused = false;
    this.startTimer(this.remaining);
    this.emit();
  }

  setSpeed(speed: PlaybackSpeed): void {
    if (speed === this.speed) return;
    this.speed = speed;
    this.onSpeedChange(speed);
    if (speed === "instant") {
      this.finish();
    } else if (this.paused) {
      // The step will start over at the new rate when it resumes.
      this.remaining = this.currentDuration();
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
      this.startTimer(this.currentDuration());
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

  private startTimer(length: number): void {
    this.timerStart = Date.now();
    this.timerLength = length;
    this.timer = setTimeout(() => this.advance(), length);
  }

  /** How long the current step shows at the current speed, its wait for the camera included. */
  currentDuration(): number {
    return this.effectDuration() + this.currentLead();
  }

  private currentLead(): number {
    if (!this.steps[this.index]) return 0;
    return leadDuration(this.leads[this.index] ?? 0, this.speed);
  }

  private effectDuration(): number {
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
    this.leads = [];
    this.index = 0;
    this.target = null;
    this.paused = false;
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
      paused: this.paused,
      current,
      index: this.index,
      total: this.steps.length,
      speed: this.speed,
      durationMs: this.effectDuration(),
      leadMs: this.currentLead(),
      target: this.target,
    };
  }

  private emit(): void {
    this.snapshot = this.makeSnapshot();
    for (const listener of this.listeners) listener();
  }
}
