/**
 * Geometry and anchors for tokens that fly between parts of the screen during playback. The
 * React side is `FlightLayer.tsx`; this module has no DOM writes, so it is testable in node.
 */

import type { Axial } from "../api";
import { hexKey } from "../hex";

export interface RectLike {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface Point {
  x: number;
  y: number;
}

/** A CSS selector, or an element already in hand. */
export type AnchorTarget = string | Element;

export function rectCenter(rect: RectLike): Point {
  return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
}

/** A rect with no area: the anchor is hidden (display: none, or not laid out). */
export function isEmptyRect(rect: RectLike): boolean {
  return rect.width === 0 && rect.height === 0;
}

/**
 * Keyframes for a token placed (centred) at `from`'s centre, flying to `to`'s centre along an
 * arc that rises by `arc` pixels at its midpoint, fading in at the start and out at the end.
 */
export function flightKeyframes(from: RectLike, to: RectLike, arc = 40): Keyframe[] {
  const a = rectCenter(from);
  const b = rectCenter(to);
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const at = (x: number, y: number, scale: number) =>
    `translate(-50%, -50%) translate(${x}px, ${y}px) scale(${scale})`;
  return [
    { offset: 0, transform: at(0, 0, 0.6), opacity: 0 },
    { offset: 0.15, transform: at(dx * 0.1, dy * 0.1 - arc * 0.4, 1), opacity: 1 },
    { offset: 0.5, transform: at(dx * 0.5, dy * 0.5 - arc, 1.05), opacity: 1 },
    { offset: 0.85, transform: at(dx * 0.9, dy * 0.9 - arc * 0.4, 1), opacity: 1 },
    { offset: 1, transform: at(dx, dy, 0.8), opacity: 0 },
  ];
}

/** Keyframes for a label that appears at an anchor, drifts up by `rise` pixels and fades. */
export function popKeyframes(rise = 24): Keyframe[] {
  const at = (y: number, scale: number) => `translate(-50%, -50%) translate(0, ${-y}px) scale(${scale})`;
  return [
    { offset: 0, transform: at(0, 0.7), opacity: 0 },
    { offset: 0.2, transform: at(rise * 0.25, 1.1), opacity: 1 },
    { offset: 0.75, transform: at(rise * 0.8, 1), opacity: 1 },
    { offset: 1, transform: at(rise, 1), opacity: 0 },
  ];
}

/** Keyframes for a ring that pulses around an anchor to draw the eye to it. */
export function highlightKeyframes(): Keyframe[] {
  return [
    { offset: 0, opacity: 0, transform: "scale(0.96)" },
    { offset: 0.25, opacity: 1, transform: "scale(1.04)" },
    { offset: 0.6, opacity: 1, transform: "scale(1)" },
    { offset: 1, opacity: 0, transform: "scale(1)" },
  ];
}

function attr(name: string, value: string): string {
  return `[${name}="${value.replace(/["\\]/g, "\\$&")}"]`;
}

/** Selectors for the data-* anchors the game views put on the things that change. */
export const anchor = {
  player: (playerId: string) => attr("data-player-id", playerId),
  cash: (playerId: string) => attr("data-cash-for", playerId),
  corp: (corpId: string) => attr("data-corp-id", corpId),
  ipo: (corpId: string) => attr("data-ipo-for", corpId),
  pool: (corpId: string) => attr("data-pool-for", corpId),
  treasury: (corpId: string) => attr("data-treasury-for", corpId),
  marketToken: (corpId: string) => attr("data-market-token", corpId),
  orderCorp: (corpId: string) => attr("data-order-corp", corpId),
  hex: (hex: Axial) => attr("data-hex", hexKey(hex)),
};

/**
 * The element `target` names, or null if it is missing or not laid out. A list is a series of
 * fallbacks, first present one wins: "the player's cash, else the player's card" is
 * `resolveAnchor([anchor.cash(id), anchor.player(id)])`.
 */
export function resolveAnchor(
  target: AnchorTarget | AnchorTarget[],
  root: Pick<ParentNode, "querySelector"> = document,
): Element | null {
  for (const candidate of Array.isArray(target) ? target : [target]) {
    const element = typeof candidate === "string" ? root.querySelector(candidate) : candidate;
    if (element && !isEmptyRect(element.getBoundingClientRect())) return element;
  }
  return null;
}
