import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import type { GameState, Planet } from "../api";
import type { PlaybackStep } from "./frames";
import { playbackSteps } from "./frames";
import { PlaybackPlayer } from "./player";
import type { PlaybackSpeed } from "./timing";
import { loadSpeed, saveSpeed } from "./timing";

const NO_PLANETS: Planet[] = [];

export interface Playback {
  /** What to draw: the step showing now while playing, else `latest`. */
  display: GameState;
  playing: boolean;
  current: PlaybackStep | null;
  index: number;
  total: number;
  speed: PlaybackSpeed;
  /** How long the current step shows; 0 when idle. */
  durationMs: number;
  /** Animates from `before` (what was on screen) to `after` (the server's reply). */
  enqueue(before: GameState, after: GameState): void;
  /** Jumps to the final state. */
  skip(): void;
  setSpeed(speed: PlaybackSpeed): void;
}

/**
 * Replays the opponents' moves in a server reply. `latest` is the newest server state; it is
 * shown whenever nothing is playing, and a playback stops if `latest` moves on to a state it does
 * not end at (an undo, or a reload). Call `enqueue` alongside setting the new state.
 *
 * `planets` (from the board) let captions name planets.
 */
export function usePlayback(latest: GameState, planets: Planet[] = NO_PLANETS): Playback {
  const [player] = useState(() => new PlaybackPlayer(loadSpeed(), saveSpeed));
  const snapshot = useSyncExternalStore(player.subscribe, player.getSnapshot);

  useEffect(() => () => player.dispose(), [player]);

  useEffect(() => {
    const target = player.getSnapshot().target;
    if (target !== null && target !== latest) player.skip();
  }, [player, latest]);

  const enqueue = useCallback(
    (before: GameState, after: GameState) => player.play(playbackSteps(before, after, planets), after),
    [player, planets],
  );
  const skip = useCallback(() => player.skip(), [player]);
  const setSpeed = useCallback((speed: PlaybackSpeed) => player.setSpeed(speed), [player]);

  return useMemo(
    () => ({
      display: snapshot.current?.state ?? latest,
      playing: snapshot.playing,
      current: snapshot.current,
      index: snapshot.index,
      total: snapshot.total,
      speed: snapshot.speed,
      durationMs: snapshot.durationMs,
      enqueue,
      skip,
      setSpeed,
    }),
    [snapshot, latest, enqueue, skip, setSpeed],
  );
}
