import { useEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "./timing";

/** Ease-out cubic: quick to start, gentle to settle. */
export function easeOut(t: number): number {
  const clamped = Math.min(1, Math.max(0, t));
  return 1 - (1 - clamped) ** 3;
}

/** The value `elapsedMs` into a tween from `from` to `to`, rounded to a whole number. */
export function tweenValue(from: number, to: number, elapsedMs: number, durationMs: number): number {
  if (durationMs <= 0 || elapsedMs >= durationMs) return to;
  return Math.round(from + (to - from) * easeOut(elapsedMs / durationMs));
}

/**
 * `target`, ticking toward each new value over `durationMs` instead of jumping. A change midway
 * starts a new tween from wherever the number has got to. Viewers who prefer reduced motion see
 * the new value at once.
 */
export function useAnimatedNumber(target: number, durationMs = 500): number {
  const [shown, setShown] = useState(target);
  const shownRef = useRef(target);

  useEffect(() => {
    const from = shownRef.current;
    if (from === target) return;
    const jump = () => {
      shownRef.current = target;
      setShown(target);
    };
    if (durationMs <= 0 || prefersReducedMotion() || typeof requestAnimationFrame !== "function") {
      jump();
      return;
    }
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const value = tweenValue(from, target, now - start, durationMs);
      shownRef.current = value;
      setShown(value);
      if (now - start < durationMs) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, durationMs]);

  return shown;
}
