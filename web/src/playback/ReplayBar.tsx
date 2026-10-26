/**
 * The replay's on-screen controls: the caption for the move playing, a step counter, the speed
 * and Skip; a banner when a new round begins; and a speed picker for places outside the replay.
 */

import type { PlaybackStep } from "./frames";
import type { PlaybackSpeed } from "./timing";
import { PLAYBACK_SPEEDS } from "./timing";
import "./playback.css";

const SPEED_LABEL: Record<string, string> = { "1": "1×", "2": "2×", "4": "4×", "8": "8×", instant: "Off" };
const SPEED_TITLE: Record<string, string> = {
  "1": "Replay opponents' moves at normal speed",
  "2": "Replay opponents' moves at double speed",
  "4": "Replay opponents' moves at four times speed",
  "8": "Replay opponents' moves at eight times speed",
  instant: "Don't replay; show the result at once",
};

interface SpeedPickerProps {
  speed: PlaybackSpeed;
  onChange: (speed: PlaybackSpeed) => void;
  /** Smaller, for the "since your move" ribbon. */
  compact?: boolean;
}

export function SpeedPicker({ speed, onChange, compact = false }: SpeedPickerProps) {
  return (
    <span className={`speed${compact ? " speed--compact" : ""}`} role="group" aria-label="Replay speed">
      {PLAYBACK_SPEEDS.map((option) => (
        <button
          key={String(option)}
          type="button"
          className={`speed__opt${option === speed ? " speed__opt--on" : ""}`}
          aria-pressed={option === speed}
          title={SPEED_TITLE[String(option)]}
          onClick={() => onChange(option)}
        >
          {SPEED_LABEL[String(option)]}
        </button>
      ))}
    </span>
  );
}

interface ReplayBarProps {
  step: PlaybackStep;
  index: number;
  total: number;
  speed: PlaybackSpeed;
  /** The colour of whoever is acting (a corporation's), or empty for a neutral bar. */
  color: string;
  onSpeed: (speed: PlaybackSpeed) => void;
  onSkip: () => void;
}

/** The caption pill shown while opponents' moves replay. */
export function ReplayBar({ step, index, total, speed, color, onSpeed, onSkip }: ReplayBarProps) {
  return (
    <div className="replay" style={color ? { ["--actor" as string]: color } : undefined}>
      <span className="replay__count num" title="Move being replayed">
        {index + 1}/{total}
      </span>
      {/* Keyed by step so each new caption fades in. */}
      <span key={index} className="replay__caption">
        {step.caption}
      </span>
      <SpeedPicker speed={speed} onChange={onSpeed} compact />
      <button type="button" className="replay__skip" onClick={onSkip} title="Skip to the end (Space or Esc)">
        Skip <kbd>Space</kbd>
      </button>
    </div>
  );
}

/** A round title across the middle of the stage while a "phase" step shows. */
export function PhaseBanner({ title }: { title: string }) {
  return (
    <div className="phase-banner" role="status">
      <span key={title} className="phase-banner__text">
        {title}
      </span>
    </div>
  );
}
