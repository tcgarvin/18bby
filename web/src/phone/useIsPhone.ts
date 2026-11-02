import { useSyncExternalStore } from "react";

/** Up to here the game takes the phone layout. A phone on its side is wider, and keeps the desktop's for now. */
const QUERY = "(max-width: 640px)";

function subscribe(listener: () => void): () => void {
  const query = window.matchMedia(QUERY);
  query.addEventListener("change", listener);
  return () => query.removeEventListener("change", listener);
}

/** True on a screen narrow enough to need the phone layout. */
export function useIsPhone(): boolean {
  return useSyncExternalStore(subscribe, () => window.matchMedia(QUERY).matches);
}
