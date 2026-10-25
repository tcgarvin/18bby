import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { GLOSSARY, rulesUrl } from "../help/glossary";
import type { GlossaryId } from "../help/glossary";
import { useRules } from "../help/rulesContext";
import { placePopover } from "../popover";
import type { Placement } from "../popover";

/** How long the popover waits before closing after the pointer leaves, so it can be reached. */
const CLOSE_DELAY_MS = 150;

/**
 * A small "?" that explains a game term. Opens on hover, focus or click; Esc or a click elsewhere
 * closes it. The popover is drawn in a portal on document.body, positioned from the trigger, so
 * no panel's overflow or white-space can clip it. The link to the full rules opens a new tab so
 * a game in progress is never lost.
 */
export function Help({ topic }: { topic: GlossaryId }) {
  const rules = useRules();
  const entry = GLOSSARY[topic];
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [placement, setPlacement] = useState<Placement | null>(null);
  const root = useRef<HTMLSpanElement>(null);
  const popover = useRef<HTMLSpanElement>(null);
  const closeTimer = useRef<number | null>(null);
  const popoverId = useId();

  const cancelClose = useCallback(() => {
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current);
    closeTimer.current = null;
  }, []);

  const closeSoon = useCallback(() => {
    if (pinned) return;
    cancelClose();
    closeTimer.current = window.setTimeout(() => setOpen(false), CLOSE_DELAY_MS);
  }, [pinned, cancelClose]);

  useEffect(() => cancelClose, [cancelClose]);

  const place = useCallback(() => {
    const trigger = root.current;
    const pop = popover.current;
    if (!trigger || !pop) return;
    const rect = pop.getBoundingClientRect();
    setPlacement(
      placePopover(trigger.getBoundingClientRect(), rect, { width: window.innerWidth, height: window.innerHeight }),
    );
  }, []);

  // Measure once the popover is in the DOM, then again whenever the page scrolls or resizes.
  useLayoutEffect(() => {
    if (!open) {
      setPlacement(null);
      return;
    }
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    function close(event: Event) {
      if (event instanceof KeyboardEvent && event.key !== "Escape") return;
      if (event instanceof MouseEvent) {
        const target = event.target as Node;
        if (root.current?.contains(target) || popover.current?.contains(target)) return;
      }
      setOpen(false);
      setPinned(false);
    }
    document.addEventListener("keydown", close);
    document.addEventListener("mousedown", close);
    return () => {
      document.removeEventListener("keydown", close);
      document.removeEventListener("mousedown", close);
    };
  }, [open]);

  return (
    <span
      ref={root}
      className="help"
      onMouseEnter={() => {
        cancelClose();
        setOpen(true);
      }}
      onMouseLeave={closeSoon}
    >
      <button
        type="button"
        className="help__btn"
        aria-label={`What is ${entry.term}?`}
        aria-expanded={open}
        aria-controls={popoverId}
        onFocus={() => setOpen(true)}
        onBlur={(e) => {
          const next = e.relatedTarget as Node | null;
          if (!root.current?.contains(next) && !popover.current?.contains(next) && !pinned) setOpen(false);
        }}
        onClick={(e) => {
          e.stopPropagation();
          setPinned((p) => !p);
          setOpen(true);
        }}
      >
        ?
      </button>
      {open &&
        createPortal(
          <span
            ref={popover}
            id={popoverId}
            role="tooltip"
            className="help__pop"
            style={placement ? { left: placement.left, top: placement.top } : { left: 0, top: 0, visibility: "hidden" }}
            onMouseEnter={cancelClose}
            onMouseLeave={closeSoon}
            // Clicks inside the popover (the rules link) must not reach a clickable card behind the "?".
            onClick={(e) => e.stopPropagation()}
          >
            <strong className="help__term">{entry.term}</strong>
            <span className="help__text">{entry.summary(rules)}</span>
            <a className="help__more" href={rulesUrl(entry.section)} target="_blank" rel="noreferrer">
              Read the full rules ↗
            </a>
          </span>,
          document.body,
        )}
    </span>
  );
}
