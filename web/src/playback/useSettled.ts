import { useEffect, useState } from "react";

/**
 * `earlier` for one frame (or for `delayMs`, if given), then `later`, so a CSS transition or a
 * "just appeared" animation runs from one to the other even in a view that has just mounted (a
 * replay step that switched views). When the two are the same value it is simply `later`.
 */
export function useSettled<T>(earlier: T, later: T, delayMs = 0): T {
  const [settled, setSettled] = useState<T | null>(null);
  useEffect(() => {
    if (earlier === later) return;
    if (delayMs > 0) {
      const timer = setTimeout(() => setSettled(() => later), delayMs);
      return () => clearTimeout(timer);
    }
    const frame = requestAnimationFrame(() => setSettled(() => later));
    return () => cancelAnimationFrame(frame);
  }, [earlier, later, delayMs]);
  return earlier === later || settled === later ? later : earlier;
}
