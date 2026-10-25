/** Placing a popover next to its trigger so it stays inside the window. */

/** Space kept between the popover and its trigger, and between the popover and the window edges. */
const GAP = 6;
const EDGE = 8;

export interface Placement {
  left: number;
  top: number;
}

/**
 * Where to put a popover of `size` for a trigger at `anchor` in a `viewport`: below the trigger,
 * or above it when there is no room below, with its left edge near the trigger's and clamped so
 * the whole popover stays inside the window.
 */
export function placePopover(
  anchor: { left: number; top: number; bottom: number },
  size: { width: number; height: number },
  viewport: { width: number; height: number },
): Placement {
  const below = anchor.bottom + GAP;
  const above = anchor.top - GAP - size.height;
  const fitsBelow = below + size.height <= viewport.height - EDGE;
  const top = fitsBelow || above < EDGE ? Math.min(below, viewport.height - EDGE - size.height) : above;
  const left = Math.min(Math.max(anchor.left - EDGE, EDGE), viewport.width - EDGE - size.width);
  return { left: Math.max(EDGE, left), top: Math.max(EDGE, top) };
}
