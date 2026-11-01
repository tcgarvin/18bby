import { useState } from "react";

/** What the map shows over its lanes: nothing more, or the focused corporation's revenue links. */
export type MapView = "regular" | "routes";

const STORAGE_KEY = "bby18.mapView";

/** The view saved in this browser, or else Regular. */
export function loadMapView(): MapView {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "routes" ? "routes" : "regular";
  } catch {
    // Storage blocked or unavailable: fall back to the default.
    return "regular";
  }
}

export function saveMapView(view: MapView): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, view);
  } catch {
    // Not saving the preference is harmless; it applies until this map unmounts.
  }
}

/**
 * The map's view and a way to choose another. The choice is remembered for the next map (views
 * remount it, so reading once at mount is enough), unless this map `startOnRoutes`: then it starts
 * on Routes every time, and flipping it applies to this map alone.
 */
export function useMapView(startOnRoutes: boolean): [MapView, (view: MapView) => void] {
  const [view, setView] = useState<MapView>(() => (startOnRoutes ? "routes" : loadMapView()));
  const choose = (next: MapView): void => {
    setView(next);
    if (!startOnRoutes) saveMapView(next);
  };
  return [view, choose];
}
