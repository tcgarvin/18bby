import { useEffect, useRef } from "react";

/**
 * A key handler keyed by `KeyboardEvent.key` (lower-cased for letters). Return false from a
 * handler to leave the event unhandled.
 */
export type KeyMap = Record<string, () => boolean | void>;

function typingInto(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName);
}

/** Normalises a keydown into the name used in a KeyMap, e.g. "p", "3", "escape", "mod+z". */
export function keyName(event: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey">): string | null {
  if (event.altKey) return null;
  const key = event.key.toLowerCase();
  return event.ctrlKey || event.metaKey ? `mod+${key}` : key;
}

/**
 * Binds single-key shortcuts while `enabled`. Keys are ignored while the user types in a form
 * field, so seat names and the sell dropdown keep working.
 */
export function useHotkeys(keys: KeyMap, enabled = true) {
  // Read the latest handlers at event time so callers can pass a fresh object each render.
  const latest = useRef(keys);
  latest.current = keys;
  useEffect(() => {
    if (!enabled) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.repeat || typingInto(event.target)) return;
      const name = keyName(event);
      const handler = name === null ? undefined : latest.current[name];
      if (handler && handler() !== false) event.preventDefault();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [enabled]);
}
