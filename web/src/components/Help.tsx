import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { GLOSSARY, rulesUrl } from "../help/glossary";
import type { GlossaryId } from "../help/glossary";
import { useRules } from "../help/rulesContext";

const POPOVER_WIDTH = 260;

/**
 * A small "?" that explains a game term. Opens on hover, focus or click; Esc or a click elsewhere
 * closes it. The link to the full rules opens a new tab so a game in progress is never lost.
 */
export function Help({ topic }: { topic: GlossaryId }) {
  const rules = useRules();
  const entry = GLOSSARY[topic];
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const root = useRef<HTMLSpanElement>(null);
  const popoverId = useId();
  const [alignRight, setAlignRight] = useState(false);

  // Keep the popover on screen: anchor it to the right edge of the "?" near the window's right side.
  useLayoutEffect(() => {
    if (!open || !root.current) return;
    setAlignRight(root.current.getBoundingClientRect().left + POPOVER_WIDTH > window.innerWidth - 8);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function close(event: Event) {
      if (event instanceof KeyboardEvent && event.key !== "Escape") return;
      if (event instanceof MouseEvent && root.current?.contains(event.target as Node)) return;
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
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => !pinned && setOpen(false)}
    >
      <button
        type="button"
        className="help__btn"
        aria-label={`What is ${entry.term}?`}
        aria-expanded={open}
        aria-controls={popoverId}
        onFocus={() => setOpen(true)}
        onBlur={(e) => {
          if (!root.current?.contains(e.relatedTarget as Node | null) && !pinned) setOpen(false);
        }}
        onClick={(e) => {
          e.stopPropagation();
          setPinned((p) => !p);
          setOpen(true);
        }}
      >
        ?
      </button>
      {open && (
        <span id={popoverId} role="tooltip" className={`help__pop${alignRight ? " help__pop--right" : ""}`}>
          <strong className="help__term">{entry.term}</strong>
          <span className="help__text">{entry.summary(rules)}</span>
          <a className="help__more" href={rulesUrl(entry.section)} target="_blank" rel="noreferrer">
            Read the full rules ↗
          </a>
        </span>
      )}
    </span>
  );
}
