import { describe, expect, it } from "vitest";
import { botLabel } from "./components/PlayerStrip";
import { difficultyLabel } from "./difficulty";

describe("difficulty labels", () => {
  it("names each difficulty for display", () => {
    expect(difficultyLabel("very-easy")).toBe("Very easy");
    expect(difficultyLabel("easy")).toBe("Easy");
  });

  it("shows an unknown key as it is", () => {
    expect(difficultyLabel("brutal")).toBe("brutal");
  });

  it("badges a bot with its difficulty, or plainly without one", () => {
    expect(botLabel("very-easy")).toBe("very easy bot");
    expect(botLabel("")).toBe("bot");
  });
});
