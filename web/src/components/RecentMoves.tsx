import type { GameState, LogEntry } from "../api";
import { SpeedPicker } from "../playback/ReplayBar";
import type { PlaybackSpeed } from "../playback/timing";
import { actorLabel, corpColor } from "../selectors";

interface RecentMovesProps {
  state: GameState;
  /** Moves played automatically (bots, forced moves) since the human's last move. */
  entries: LogEntry[];
  /** Whether any of them changed the map (those hexes are outlined). */
  mapChanged: boolean;
  /** Replay speed, offered here so it can be changed back from "off". */
  speed: PlaybackSpeed;
  onSpeed: (speed: PlaybackSpeed) => void;
  /** Replays these moves again; null when they cannot be (an opening, or the game moved on). */
  onReplay: (() => void) | null;
  onShowLog: () => void;
  onDismiss: () => void;
}

const SHOWN = 6;

/**
 * A one-line ribbon under the top bar: what others did since your move. It appears once their
 * moves have replayed (at once when replay is off), as a summary to glance back at.
 */
export function RecentMoves({ state, entries, mapChanged, speed, onSpeed, onReplay, onShowLog, onDismiss }: RecentMovesProps) {
  const shown = entries.slice(-SHOWN);
  const earlier = entries.length - shown.length;
  return (
    <div className="ribbon" role="status">
      <span className="ribbon__label">
        Since your move
        {mapChanged && <span className="ribbon__note"> · outlined on the map</span>}
      </span>
      <ol className="ribbon__list">
        {shown.map((entry) => {
          const isCorp = state.corporations.some((c) => c.id === entry.actor);
          return (
            <li key={entry.seq}>
              <span className="ribbon__actor" style={isCorp ? { color: corpColor(state, entry.actor) } : undefined}>
                {actorLabel(state, entry.actor)}
              </span>{" "}
              {entry.text}
            </li>
          );
        })}
      </ol>
      {onReplay && (
        <button type="button" className="link" onClick={onReplay} title="Replay these moves">
          watch again
        </button>
      )}
      <SpeedPicker speed={speed} onChange={onSpeed} compact />
      <button type="button" className="link" onClick={onShowLog}>
        {earlier > 0 ? `+${earlier} in log` : "log"}
      </button>
      <button type="button" className="link ribbon__hide" onClick={onDismiss}>
        hide
      </button>
    </div>
  );
}
