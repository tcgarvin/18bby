/**
 * An overlay for playback effects: tokens that fly between anchors, labels that pop up at one,
 * and rings that highlight one. Anchors are found by selector when the effect starts, so a view
 * only needs the data-* attributes in `anchor`; a missing anchor makes the effect a no-op.
 */

import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useMemo, useRef } from "react";
import { createPortal } from "react-dom";
import type { AnchorTarget } from "./flight";
import { flightKeyframes, highlightKeyframes, popKeyframes, rectCenter, resolveAnchor } from "./flight";
import { prefersReducedMotion } from "./timing";

/** What a flying or popping token looks like. */
export type TokenVariant = "chip" | "coin" | "label";

export interface FlyOptions {
  /** Where the token starts; a list is a series of fallbacks. */
  from: AnchorTarget | AnchorTarget[];
  to: AnchorTarget | AnchorTarget[];
  label: string;
  /** Background for chips, text colour for coins and labels. */
  color?: string;
  variant?: TokenVariant;
  durationMs?: number;
  delayMs?: number;
}

export interface PopOptions {
  at: AnchorTarget | AnchorTarget[];
  label: string;
  color?: string;
  variant?: TokenVariant;
  durationMs?: number;
  delayMs?: number;
}

export interface HighlightOptions {
  target: AnchorTarget | AnchorTarget[];
  color?: string;
  durationMs?: number;
  delayMs?: number;
}

export interface FlightApi {
  /** Resolves when the token lands, or at once if an anchor is missing. */
  fly(options: FlyOptions): Promise<void>;
  pop(options: PopOptions): Promise<void>;
  highlight(options: HighlightOptions): Promise<void>;
  /** Ends every effect in progress, e.g. when playback is skipped. */
  clear(): void;
}

const done = Promise.resolve();

const NO_FLIGHTS: FlightApi = {
  fly: () => done,
  pop: () => done,
  highlight: () => done,
  clear: () => {},
};

const FlightContext = createContext<FlightApi>(NO_FLIGHTS);

/** The playback effects API; a no-op outside a `FlightLayer`. */
export function useFlight(): FlightApi {
  return useContext(FlightContext);
}

const EASING = "cubic-bezier(0.4, 0, 0.2, 1)";

function tokenStyle(variant: TokenVariant, color: string): Partial<CSSStyleDeclaration> {
  const base: Partial<CSSStyleDeclaration> = {
    position: "fixed",
    whiteSpace: "nowrap",
    fontFamily: "var(--font-mono, monospace)",
    fontWeight: "600",
    fontSize: "12px",
    lineHeight: "1",
    pointerEvents: "none",
    willChange: "transform, opacity",
    opacity: "0",
  };
  if (variant === "chip") {
    return { ...base, background: color, color: "#fff", padding: "4px 7px", borderRadius: "4px", boxShadow: "0 2px 6px rgb(0 0 0 / 0.25)" };
  }
  if (variant === "coin") {
    return { ...base, background: "#f5c542", color: "#3d2e00", padding: "4px 7px", borderRadius: "999px", border: "1px solid #c9971c", boxShadow: "0 2px 6px rgb(0 0 0 / 0.25)" };
  }
  return { ...base, color, fontSize: "14px", textShadow: "0 0 3px var(--surface, #fff), 0 0 3px var(--surface, #fff)" };
}

function token(label: string, variant: TokenVariant, color: string, left: number, top: number): HTMLElement {
  const element = document.createElement("div");
  element.textContent = label;
  Object.assign(element.style, tokenStyle(variant, color), { left: `${left}px`, top: `${top}px` });
  return element;
}

/** Provides `useFlight` to its children and draws the effects above everything else. */
export function FlightLayer({ children }: { children: ReactNode }) {
  const overlay = useRef<HTMLDivElement>(null);
  const running = useRef(new Set<Animation>());

  const run = useCallback((element: HTMLElement, keyframes: Keyframe[], durationMs: number, delayMs: number) => {
    const layer = overlay.current;
    if (!layer || typeof element.animate !== "function") return done;
    layer.appendChild(element);
    const animation = element.animate(keyframes, { duration: durationMs, delay: delayMs, easing: EASING, fill: "both" });
    running.current.add(animation);
    const cleanUp = () => {
      running.current.delete(animation);
      element.remove();
    };
    // A cancelled animation rejects `finished`; either way the effect is over.
    return animation.finished.then(cleanUp, cleanUp);
  }, []);

  const api = useMemo<FlightApi>(() => {
    if (prefersReducedMotion()) return NO_FLIGHTS;
    return {
      fly({ from, to, label, color = "var(--accent, #1f5fa8)", variant = "chip", durationMs = 700, delayMs = 0 }) {
        const start = resolveAnchor(from);
        const end = resolveAnchor(to);
        if (!start || !end) return done;
        const a = start.getBoundingClientRect();
        const center = rectCenter(a);
        const element = token(label, variant, color, center.x, center.y);
        return run(element, flightKeyframes(a, end.getBoundingClientRect()), durationMs, delayMs);
      },
      pop({ at, label, color = "var(--ink, #1b2330)", variant = "label", durationMs = 900, delayMs = 0 }) {
        const target = resolveAnchor(at);
        if (!target) return done;
        const center = rectCenter(target.getBoundingClientRect());
        return run(token(label, variant, color, center.x, center.y), popKeyframes(), durationMs, delayMs);
      },
      highlight({ target, color = "var(--accent, #1f5fa8)", durationMs = 900, delayMs = 0 }) {
        const element = resolveAnchor(target);
        if (!element) return done;
        const rect = element.getBoundingClientRect();
        const ring = document.createElement("div");
        const pad = 4;
        Object.assign(ring.style, {
          position: "fixed",
          left: `${rect.left - pad}px`,
          top: `${rect.top - pad}px`,
          width: `${rect.width + pad * 2}px`,
          height: `${rect.height + pad * 2}px`,
          border: `2px solid ${color}`,
          borderRadius: "var(--radius, 8px)",
          boxShadow: `0 0 10px ${color}`,
          pointerEvents: "none",
          opacity: "0",
        });
        return run(ring, highlightKeyframes(), durationMs, delayMs);
      },
      clear() {
        for (const animation of running.current) animation.cancel();
      },
    };
  }, [run]);

  return (
    <FlightContext.Provider value={api}>
      {children}
      {createPortal(
        <div
          ref={overlay}
          aria-hidden="true"
          style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 1000, overflow: "hidden" }}
        />,
        document.body,
      )}
    </FlightContext.Provider>
  );
}
