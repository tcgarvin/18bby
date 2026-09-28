import type { LogEntry } from "./api";

function sameEntry(a: LogEntry, b: LogEntry): boolean {
  return a.round === b.round && a.actor === b.actor && a.text === b.text;
}

/**
 * Entries in `next` that were not in `previous`.
 *
 * The server only returns the most recent 200 entries, so comparing lengths is not enough once
 * the log is full. Instead, find the longest suffix of `previous` that is also a prefix of
 * `next`; whatever follows that overlap is new.
 */
export function newLogEntries(previous: LogEntry[], next: LogEntry[]): LogEntry[] {
  for (let overlap = Math.min(previous.length, next.length); overlap > 0; overlap--) {
    const tail = previous.slice(previous.length - overlap);
    if (tail.every((entry, i) => sameEntry(entry, next[i]))) {
      return next.slice(overlap);
    }
  }
  return next;
}
