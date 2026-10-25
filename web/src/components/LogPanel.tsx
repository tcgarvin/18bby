import { useEffect, useRef } from "react";
import type { GameState, LogEntry } from "../api";
import { actorLabel } from "../selectors";

interface LogPanelProps {
  state: GameState;
  /** Entries added by the last request, highlighted. */
  fresh: LogEntry[];
}

/** The game log, newest at the bottom, scrolled to the end when it opens. */
export function LogPanel({ state, fresh }: LogPanelProps) {
  const listRef = useRef<HTMLOListElement>(null);
  const freshSeqs = new Set(fresh.map((entry) => entry.seq));

  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [state.log]);

  return (
    <ol className="log" ref={listRef}>
      {state.log.map((entry) => (
        <li key={entry.seq} className={freshSeqs.has(entry.seq) ? "log__entry log__entry--fresh" : "log__entry"}>
          <span className="log__round">{entry.round}</span>
          <span className="log__actor">{actorLabel(state, entry.actor)}</span>
          <span className="log__text">{entry.text}</span>
        </li>
      ))}
      {state.log.length === 0 && <li className="muted">Nothing yet.</li>}
    </ol>
  );
}
