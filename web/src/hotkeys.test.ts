import { describe, expect, it } from "vitest";
import { keyName } from "./hotkeys";

const press = (key: string, mods: Partial<{ ctrlKey: boolean; metaKey: boolean; altKey: boolean }> = {}) =>
  keyName({ key, ctrlKey: false, metaKey: false, altKey: false, ...mods });

describe("keyName", () => {
  it("lower-cases letters and named keys", () => {
    expect(press("P")).toBe("p");
    expect(press("Escape")).toBe("escape");
    expect(press("3")).toBe("3");
  });

  it("folds ctrl and cmd into mod", () => {
    expect(press("z", { ctrlKey: true })).toBe("mod+z");
    expect(press("Z", { metaKey: true })).toBe("mod+z");
  });

  it("ignores alt chords", () => {
    expect(press("p", { altKey: true })).toBeNull();
  });
});
