import type { RefObject } from "react";
import { useLayoutEffect, useRef } from "react";

function parseBox(box: string): number[] {
  return box.split(" ").map(Number);
}

/** The view `t` of the way from `from` to `to` (0 to 1), easing in and out. */
export function interpolateBox(from: string, to: string, t: number): string {
  const eased = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
  const end = parseBox(to);
  return parseBox(from)
    .map((value, i) => (value + (end[i] - value) * eased).toFixed(1))
    .join(" ");
}

/**
 * Moves an SVG's `viewBox` to `box` over `glideMs` rather than jumping. React has already written
 * `box` when this runs, before paint, so the attribute is put back and walked forward; it won't
 * write it again until `box` changes. With no `glideMs` the jump stands.
 */
export function useViewBoxGlide(svg: RefObject<SVGSVGElement | null>, box: string, glideMs: number): void {
  const shown = useRef(box);

  useLayoutEffect(() => {
    const element = svg.current;
    const from = shown.current;
    if (element === null || from === box) return;
    if (glideMs <= 0) {
      shown.current = box;
      return;
    }
    const startedAt = performance.now();
    let frame = 0;
    const draw = (now: number) => {
      const t = Math.min(1, (now - startedAt) / glideMs);
      shown.current = t === 1 ? box : interpolateBox(from, box, t);
      element.setAttribute("viewBox", shown.current);
      if (t < 1) frame = requestAnimationFrame(draw);
    };
    element.setAttribute("viewBox", from);
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [svg, box, glideMs]);
}
