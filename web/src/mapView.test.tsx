import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { loadMapView, saveMapView, useMapView, type MapView } from "./mapView";

function fakeStorage(): Storage {
  const items = new Map<string, string>();
  return {
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => void items.set(key, value),
  } as unknown as Storage;
}

function throwingStorage(): Storage {
  const blocked = () => {
    throw new Error("storage blocked");
  };
  return { getItem: blocked, setItem: blocked } as unknown as Storage;
}

/** What the hook gives a map as it mounts. (Server rendering ignores the state update, not the save.) */
function mount(startOnRoutes: boolean): { view: MapView; choose: (view: MapView) => void } {
  let result: { view: MapView; choose: (view: MapView) => void } | undefined;
  function Probe() {
    const [view, choose] = useMapView(startOnRoutes);
    result = { view, choose };
    return null;
  }
  renderToStaticMarkup(<Probe />);
  if (result === undefined) throw new Error("the probe did not render");
  return result;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("mapView", () => {
  it("defaults to Regular", () => {
    vi.stubGlobal("window", { localStorage: fakeStorage() });
    expect(loadMapView()).toBe("regular");
  });

  it("remembers the choice for the next map", () => {
    vi.stubGlobal("window", { localStorage: fakeStorage() });
    mount(false).choose("routes");
    expect(mount(false).view).toBe("routes");
    mount(false).choose("regular");
    expect(mount(false).view).toBe("regular");
  });

  it("ignores a stored value it does not know", () => {
    const localStorage = fakeStorage();
    localStorage.setItem("bby18.mapView", "sideways");
    vi.stubGlobal("window", { localStorage });
    expect(loadMapView()).toBe("regular");
  });

  it("survives storage that throws, and having no window at all", () => {
    vi.stubGlobal("window", { localStorage: throwingStorage() });
    expect(loadMapView()).toBe("regular");
    expect(() => saveMapView("routes")).not.toThrow();
    vi.unstubAllGlobals();
    vi.stubGlobal("window", undefined);
    expect(loadMapView()).toBe("regular");
    expect(() => saveMapView("routes")).not.toThrow();
  });

  it("starts a startOnRoutes map on Routes whatever is remembered", () => {
    vi.stubGlobal("window", { localStorage: fakeStorage() });
    saveMapView("regular");
    expect(mount(true).view).toBe("routes");
  });

  it("does not let a startOnRoutes map overwrite the remembered choice", () => {
    vi.stubGlobal("window", { localStorage: fakeStorage() });
    saveMapView("routes");
    mount(true).choose("regular");
    expect(loadMapView()).toBe("routes");
  });
});
