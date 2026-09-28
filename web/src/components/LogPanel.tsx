import { useEffect, useRef } from "react";
import type { GameState, LogEntry } from "../api";
import { playerName } from "../selectors";

interface LogPanelProps {
  state: GameState;
  /** Entries added since the previous state, highlighted. */
  fresh: LogEntry[];
}

export function actorLabel(state: GameState, actor: string): string {
  return state.corporations.some((c) => c.id === actor) ? actor : playerName(state, actor);
}

export function LogPanel({ state, fresh }: LogPanelProps) {
  const listRef = useRef<HTMLOListElement>(null);
  const firstFresh = state.log.length - fresh.length;

  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [state.log]);

  return (
    <section className="panel panel--log">
      <h2 className="panel__title">Log</h2>
      <ol className="log" ref={listRef}>
        {state.log.map((entry, i) => (
          <li key={i} className={i >= firstFresh ? "log__entry log__entry--fresh" : "log__entry"}>
            <span className="log__round">{entry.round}</span>
            <span className="log__actor">{actorLabel(state, entry.actor)}</span>
            <span className="log__text">{entry.text}</span>
          </li>
        ))}
        {state.log.length === 0 && <li className="muted">Nothing yet.</li>}
      </ol>
    </section>
  );
}
