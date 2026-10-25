import { describe, expect, it } from "vitest";
import type { GameState, MoveFrame, Planet } from "../api";
import { corporation, gameState, logEntry, moveFrame, withCorp, withPlayer } from "./fixtures";
import { applyFrame, describeHex, describeMove, displayStates, moveKind, playbackSteps, roundTitle } from "./frames";

const PLANETS: Planet[] = [
  { name: "Kuat", hex: [-3, 2], region: "Core", tags: ["S"] },
  { name: "Corellia", hex: [0, 0], region: "Core", tags: ["I"] },
];

/** SR1: Tim (human) starts CEC, Selka buys a share, Rax passes, and it is Tim's turn again. */
function stockRound() {
  const before = gameState({ log: [logEntry(0, "Tim", "joins")] });
  const started = withPlayer(
    withCorp(before, "CEC", { status: "parred", par: 70, ipoPrice: 70, price: 70, marketCell: [0, 1], ipoShares: 8, president: "P1" }),
    "P1",
    { cash: 260, shares: { CEC: 2 }, certificates: 1 },
  );
  const submitted = moveFrame({ type: "buy", corp: "CEC", source: "ipo", par: 70 }, { ...started, currentPlayer: "P2" }, {
    actor: "P1",
    automatic: false,
    log: [logEntry(1, "Tim", "starts CEC at par 70")],
  });
  const bought = withPlayer(withCorp(started, "CEC", { ipoShares: 7 }), "P2", { cash: 330, shares: { CEC: 1 }, certificates: 1 });
  const buy = moveFrame({ type: "buy", corp: "CEC", source: "ipo" }, { ...bought, currentPlayer: "P3" }, {
    actor: "P2",
    log: [logEntry(2, "Selka Darrow", "buys CEC from ipo for 70")],
  });
  const pass = moveFrame({ type: "pass" }, { ...bought, currentPlayer: "P1" }, {
    actor: "P3",
    log: [logEntry(3, "Admiral Rax", "passes")],
  });
  const after: GameState = {
    ...bought,
    currentPlayer: "P1",
    legalActions: [{ type: "pass" }],
    log: [logEntry(0, "Tim", "joins"), ...[submitted, buy, pass].flatMap((f) => f.log)],
    automaticLogStart: 2,
    canUndo: true,
    moves: [submitted, buy, pass],
  };
  return { before, after, submitted, buy, pass };
}

/** OR1.1: KDY (president Rax) is operating with 300 in its treasury. */
function operating(): GameState {
  const base = gameState({
    phase: "network",
    roundLabel: "OR1.1",
    currentPlayer: "P3",
    currentCorporation: "KDY",
    operatingOrder: ["KDY", "CEC"],
    tiles: [{ hex: [-4, 2], exits: ["E", "W"], service: ["CEC"] }],
    corporations: [
      corporation("CEC", { status: "floated", par: 70, price: 70, treasury: 100, president: "P1", ipoShares: 0 }),
      corporation("KDY", { status: "floated", par: 70, price: 120, treasury: 300, president: "P3", ipoShares: 4, poolShares: 1 }),
    ],
  });
  return withPlayer(withPlayer(base, "P2", { shares: { KDY: 2 } }), "P3", { shares: { KDY: 3 } });
}

describe("applyFrame", () => {
  it("merges players by id, keeping names and seat details", () => {
    const { before, submitted } = stockRound();
    const next = applyFrame(before, submitted);
    expect(next.players.map((p) => [p.id, p.name, p.isBot, p.cash])).toEqual([
      ["P1", "Tim", false, 260],
      ["P2", "Selka Darrow", true, 400],
      ["P3", "Admiral Rax", true, 400],
    ]);
    expect(next.players[0].shares).toEqual({ CEC: 2 });
  });

  it("replaces corporations and copies turn fields", () => {
    const { before, submitted } = stockRound();
    const next = applyFrame(before, submitted);
    expect(next.corporations).toBe(submitted.after.corporations);
    expect(next.currentPlayer).toBe("P2");
  });

  it("clears actions so nothing is clickable mid-replay", () => {
    const { before, submitted } = stockRound();
    const next = applyFrame(before, submitted);
    expect(next.legalActions).toEqual([]);
    expect(next.waitingOnHuman).toBe(false);
    expect(next.moves).toEqual([]);
  });

  it("merges tiles by hex, replacing changed ones and adding new ones", () => {
    const base = operating();
    const upgraded = { hex: [-4, 2] as [number, number], exits: ["E" as const, "W" as const, "NW" as const], service: ["CEC", "KDY"] };
    const charted = { hex: [-3, 1] as [number, number], exits: ["E" as const, "SE" as const], service: ["KDY"] };
    const frame = moveFrame({ type: "upgrade", hex: [-4, 2], exit: "NW", cost: 80 }, base, { actor: "P3", tiles: [upgraded, charted] });
    expect(applyFrame(base, frame).tiles).toEqual([upgraded, charted]);
  });

  it("appends log lines without repeating ones already shown", () => {
    const base = gameState({ log: [logEntry(0, "Tim", "a"), logEntry(1, "Tim", "b")] });
    const frame = moveFrame({ type: "pass" }, base, { actor: "P1", log: [logEntry(1, "Tim", "b"), logEntry(2, "Tim", "passes")] });
    expect(applyFrame(base, frame).log.map((e) => e.seq)).toEqual([0, 1, 2]);
  });
});

describe("playbackSteps and displayStates", () => {
  it("skips the submitted move but starts from its result", () => {
    const { before, after } = stockRound();
    const steps = playbackSteps(before, after);
    expect(steps.map((step) => step.frame?.actor)).toEqual(["P2", "P3"]);
    // Selka's buy is shown on top of Tim's start, not the original state.
    expect(steps[0].before.players[0].cash).toBe(260);
    expect(steps[0].state.players[1].cash).toBe(330);
  });

  it("ends exactly at the server's state", () => {
    const { before, after } = stockRound();
    const states = displayStates(before, after);
    expect(states).toHaveLength(3);
    expect(states[2]).toBe(after);
    expect(states[0].legalActions).toEqual([]);
    expect(states[1].legalActions).toEqual([]);
  });

  it("shows each move in its own turn, with the results of the move", () => {
    const { before, after } = stockRound();
    const [buy, pass] = playbackSteps(before, after);
    // Selka's buy is shown as Selka's turn, though the server has moved on to Rax.
    expect(buy.state.currentPlayer).toBe("P2");
    expect(buy.state.players[1].cash).toBe(330);
    expect(pass.state.currentPlayer).toBe("P3");
  });

  it("shows a dividend on the dividend view, not the next corporation's map", () => {
    const prev = withCorp(gameState({ phase: "dividend", roundLabel: "OR1.1", currentPlayer: "P3", currentCorporation: "KDY", operatingOrder: ["KDY", "CEC"] }), "KDY", { status: "floated", price: 70 });
    const paidOn = withCorp({ ...prev, phase: "network", currentCorporation: "CEC", currentPlayer: "P1" }, "KDY", { price: 80 });
    const frame = moveFrame({ type: "dividend", choice: "pay" }, paidOn, { actor: "P3", corporation: "KDY", phase: "dividend", revenue: 60 });
    const [step] = playbackSteps(prev, { ...paidOn, moves: [frame] });
    expect(step.state).toMatchObject({ phase: "dividend", currentCorporation: "KDY", currentPlayer: "P3" });
    expect(step.state.corporations[1].price).toBe(80);
    expect(step.before.corporations[1].price).toBe(70);
  });

  it("is just the final state when there are no moves", () => {
    const { before, after } = stockRound();
    const reloaded = { ...after, moves: [] };
    expect(displayStates(before, reloaded)).toEqual([reloaded]);
    expect(playbackSteps(before, reloaded)).toEqual([]);
  });

  it("copes with a server that sends no moves at all", () => {
    const { before, after } = stockRound();
    const old = { ...after } as Partial<GameState>;
    delete old.moves;
    expect(displayStates(before, old as GameState)).toEqual([old]);
  });

  it("is just the final state when only the submitted move was played", () => {
    const { before, after, submitted } = stockRound();
    const states = displayStates(before, { ...after, moves: [submitted] });
    expect(states).toHaveLength(1);
    expect(states[0].moves).toEqual([submitted]);
  });

  it("adds a banner when the round changes", () => {
    const { before, after, pass } = stockRound();
    const operatingNow = { ...pass, after: { ...pass.after, phase: "network" as const, roundLabel: "OR1.1" } };
    const final = { ...after, phase: "network" as const, roundLabel: "OR1.1", moves: [after.moves[0], after.moves[1], operatingNow] };
    const steps = playbackSteps(before, final);
    expect(steps.map((s) => s.kind.kind)).toEqual(["buy", "pass", "phase"]);
    expect(steps[2].caption).toBe("Operating round 1.1");
    expect(steps[2].state).toBe(final);
    expect(steps[1].state).not.toBe(final);
  });

  it("shows a banner for a round change caused by the submitted move", () => {
    const { before, after, submitted } = stockRound();
    const ending = { ...submitted, after: { ...submitted.after, phase: "network" as const, roundLabel: "OR1.1" } };
    const steps = playbackSteps(before, { ...after, phase: "network", roundLabel: "OR1.1", moves: [ending] });
    expect(steps.map((s) => s.kind.kind)).toEqual(["phase"]);
  });
});

describe("moveKind and describeMove: stock round", () => {
  it("describes starting a corporation", () => {
    const { before, submitted } = stockRound();
    expect(moveKind(submitted, before)).toMatchObject({ kind: "buy", player: "P1", corp: "CEC", par: 70, shares: 2, cost: 140, newPresident: "P1" });
    expect(describeMove(submitted, before)).toBe("Tim starts CEC at par 70");
  });

  it("describes buying from the IPO, and notes floating", () => {
    const { before, after, submitted, buy } = stockRound();
    const prev = applyFrame(before, submitted);
    const kind = moveKind(buy, prev);
    expect(kind).toMatchObject({ kind: "buy", player: "P2", source: "ipo", shares: 1, cost: 70, floated: false, newPresident: null });
    expect(kind).not.toHaveProperty("par");
    expect(describeMove(buy, prev)).toBe("Selka Darrow buys a CEC share from the IPO for 70");

    const floats = { ...buy, after: { ...buy.after, corporations: withCorp(after, "CEC", { status: "floated", treasury: 560 }).corporations } };
    expect(moveKind(floats, prev)).toMatchObject({ floated: true, treasuryGain: 560 });
    expect(describeMove(floats, prev)).toBe("Selka Darrow buys a CEC share from the IPO for 70; CEC floats");
  });

  it("describes buying from the pool and taking the presidency", () => {
    const prev = operating();
    const after = withPlayer(withCorp(prev, "KDY", { poolShares: 0, president: "P2" }), "P2", { cash: 280, shares: { KDY: 4 } });
    const frame = moveFrame({ type: "buy", corp: "KDY", source: "pool" }, after, { actor: "P2" });
    expect(moveKind(frame, prev)).toMatchObject({ kind: "buy", source: "pool", cost: 120, newPresident: "P2" });
    expect(describeMove(frame, prev)).toBe("Selka Darrow buys a KDY share from the pool for 120; Selka Darrow becomes president");
  });

  it("describes a sale with its price drop", () => {
    const prev = operating();
    const after = withPlayer(withCorp(prev, "KDY", { poolShares: 3, price: 100 }), "P2", { cash: 640, shares: {} });
    const frame = moveFrame({ type: "sell", corp: "KDY", count: 2 }, after, { actor: "P2" });
    expect(moveKind(frame, prev)).toMatchObject({ kind: "sell", count: 2, proceeds: 240, price: { before: 120, after: 100 } });
    expect(describeMove(frame, prev)).toBe("Selka Darrow sells 2 KDY for 240; price 120 → 100");
  });

  it("describes a pass, and a sold-out rise at the round's end", () => {
    const { after, pass } = stockRound();
    expect(moveKind(pass, after)).toEqual({ kind: "pass", player: "P3", priceChanges: [] });
    expect(describeMove(pass, after)).toBe("Admiral Rax passes");

    const soldOut = { ...pass, after: { ...pass.after, corporations: withCorp(after, "CEC", { price: 80 }).corporations } };
    expect(describeMove(soldOut, after)).toBe("Admiral Rax passes; CEC sold out, price 70 → 80");
  });
});

describe("moveKind and describeMove: operating round", () => {
  const network = (action: MoveFrame["action"], treasury: number) =>
    moveFrame(action, withCorp(operating(), "KDY", { treasury }), { actor: "P3", corporation: "KDY" });

  it("describes charting, naming the planet next door", () => {
    const frame = network({ type: "chart", hex: [-3, 1], exits: ["E", "SE"], cost: 60 }, 240);
    expect(moveKind(frame, operating())).toEqual({ kind: "chart", corp: "KDY", hex: [-3, 1], exits: ["E", "SE"], cost: 60 });
    expect(describeMove(frame, operating(), PLANETS)).toBe("KDY charts a lane at (−3,1) near Kuat for 60");
    expect(describeMove(frame, operating())).toBe("KDY charts a lane at (−3,1) for 60");
  });

  it("describes an upgrade and a service extension", () => {
    const upgrade = network({ type: "upgrade", hex: [-4, 2], exit: "NW", cost: 80 }, 220);
    expect(moveKind(upgrade, operating())).toMatchObject({ kind: "upgrade", exit: "NW", cost: 80 });
    expect(describeMove(upgrade, operating(), PLANETS)).toBe("KDY adds a NW exit at (−4,2) near Kuat for 80");
    const service = network({ type: "service", hex: [-4, 2], cost: 60 }, 240);
    expect(describeMove(service, operating(), PLANETS)).toBe("KDY extends service to (−4,2) near Kuat for 60");
  });

  it("describes taking no network action", () => {
    const frame = network({ type: "no_action" }, 300);
    expect(moveKind(frame, operating())).toEqual({ kind: "no_action", corp: "KDY" });
    expect(describeMove(frame, operating())).toBe("KDY takes no network action");
  });

  it("works out a dividend's payouts from cash changes", () => {
    const prev = { ...operating(), phase: "dividend" as const };
    const paid = withCorp(withPlayer(withPlayer(prev, "P2", { cash: 426 }), "P3", { cash: 439 }), "KDY", { price: 140 });
    const frame = moveFrame({ type: "dividend", choice: "pay" }, paid, { actor: "P3", corporation: "KDY", revenue: 130 });
    expect(moveKind(frame, prev)).toEqual({
      kind: "dividend",
      corp: "KDY",
      pay: true,
      revenue: 130,
      perShare: 13,
      payouts: { P2: 26, P3: 39 },
      treasuryGain: 0,
      price: { corp: "KDY", before: 120, after: 140 },
    });
    expect(describeMove(frame, prev)).toBe("KDY pays 130 — 13 per share; price 120 → 140");
  });

  it("describes withholding", () => {
    const prev = { ...operating(), phase: "dividend" as const };
    const kept = withCorp(prev, "KDY", { treasury: 390, price: 100 });
    const frame = moveFrame({ type: "dividend", choice: "withhold" }, kept, { actor: "P3", corporation: "KDY", revenue: 90 });
    expect(moveKind(frame, prev)).toMatchObject({ pay: false, payouts: {}, treasuryGain: 90 });
    expect(describeMove(frame, prev)).toBe("KDY withholds 90; price 120 → 100");
    const nothing = moveFrame({ type: "dividend", choice: "withhold" }, prev, { actor: "P3", corporation: "KDY", revenue: 0 });
    expect(describeMove(nothing, prev)).toBe("KDY earns nothing; price stays 120");
  });

  it("falls back to the log for an action it does not know", () => {
    const prev = operating();
    const frame = {
      ...moveFrame({ type: "no_action" }, prev, { actor: "P3", log: [logEntry(9, "KDY", "does something new")] }),
      action: { type: "teleport" } as unknown as MoveFrame["action"],
    };
    expect(moveKind(frame, prev)).toEqual({ kind: "unknown", actor: "P3" });
    expect(describeMove(frame, prev)).toBe("KDY does something new");
  });
});

describe("captions", () => {
  it("names the planet a hex is on", () => {
    expect(describeHex([0, 0], PLANETS)).toBe("Corellia (0,0)");
    expect(describeHex([5, 5], PLANETS)).toBe("(5,5)");
  });

  it("titles rounds", () => {
    expect(roundTitle("stock", "SR2")).toBe("Stock round 2");
    expect(roundTitle("network", "OR1.2")).toBe("Operating round 1.2");
    expect(roundTitle("game_over", "end")).toBe("Game over");
  });
});

describe("network action count in replay", () => {
  it("counts a corporation's first and second actions as 1 and 2", () => {
    const before = operating();
    const first = { ...before, networkActionsTaken: 1 };
    // After its last action the corporation moves on to its dividend.
    const second: GameState = { ...first, phase: "dividend", networkActionsTaken: 2 };
    const chart = moveFrame({ type: "chart", hex: [-3, 1], exits: ["E", "SE"], cost: 60 }, first, {
      actor: "P3",
      corporation: "KDY",
      phase: "network",
    });
    const service = moveFrame({ type: "service", hex: [-4, 2], cost: 60 }, second, {
      actor: "P3",
      corporation: "KDY",
      phase: "network",
    });
    const after: GameState = { ...second, moves: [chart, service] };
    const steps = playbackSteps(before, after);
    expect(steps.map((s) => s.state.networkActionsTaken)).toEqual([1, 2]);
  });
});
