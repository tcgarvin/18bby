import type { LogEntry } from "./api";

/**
 * Entries in `next` that were not in `previous`.
 *
 * The server numbers every log line with a `seq` that survives the 200-line cap, so anything
 * newer than the last entry we had is new.
 */
export function newLogEntries(previous: LogEntry[], next: LogEntry[]): LogEntry[] {
  if (previous.length === 0) return next;
  const lastSeen = previous[previous.length - 1].seq;
  return next.filter((entry) => entry.seq > lastSeen);
}
