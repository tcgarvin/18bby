import { useEffect } from "react";
import { playEffects } from "./choreography";
import { useFlight } from "./FlightLayer";
import type { PlaybackStep } from "./frames";

interface StepEffectsProps {
  /** The step showing, or null when nothing plays. */
  step: PlaybackStep | null;
  durationMs: number;
  color: (corpId: string) => string;
}

/**
 * Plays each step's flights and highlights as it starts, and clears them when playback ends or
 * is skipped. Renders nothing; it must sit inside a `FlightLayer`.
 */
export function StepEffects({ step, durationMs, color }: StepEffectsProps) {
  const flight = useFlight();

  useEffect(() => {
    if (step === null) {
      flight.clear();
      return;
    }
    // Wait two frames: a step that switches views needs the new view laid out before its
    // anchors can be measured.
    let frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(() => playEffects(step, flight, durationMs, color));
    });
    return () => cancelAnimationFrame(frame);
    // Keyed on the step alone: `color` and `durationMs` are read when it starts, and callers
    // rebuild `color` on every render.
  }, [step, flight]);

  return null;
}
