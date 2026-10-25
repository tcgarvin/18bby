/**
 * Which effects each kind of step plays, and between which anchors. Pure, so views only call
 * `playEffects(step, flight, ...)` when a step starts.
 */

import type { FlightApi, FlyOptions, HighlightOptions, PopOptions } from "./FlightLayer";
import { anchor } from "./flight";
import type { MoveKind, PlaybackStep } from "./frames";

export type Effect =
  | ({ effect: "fly" } & FlyOptions)
  | ({ effect: "pop" } & PopOptions)
  | ({ effect: "highlight" } & HighlightOptions);

const GAIN = "#1e7b3c";
const LOSS = "#b3261e";

const signed = (amount: number) => (amount >= 0 ? `+${amount}` : `−${-amount}`);

/**
 * The effects for `kind`, timed to fit in a step of `durationMs`. `color` gives each
 * corporation's colour. Phase banners are the view's job, so they have no effects here.
 */
export function effectsFor(kind: MoveKind, durationMs: number, color: (corpId: string) => string): Effect[] {
  const travel = Math.round(durationMs * 0.6);
  const settle = Math.round(durationMs * 0.5);
  const later = Math.round(durationMs * 0.35);
  const money = (at: string[], amount: number, delayMs = 0): Effect => ({
    effect: "pop",
    at,
    label: signed(amount),
    color: amount >= 0 ? GAIN : LOSS,
    durationMs: settle,
    delayMs,
  });
  switch (kind.kind) {
    case "buy": {
      const source = kind.source === "ipo" ? anchor.ipo(kind.corp) : anchor.pool(kind.corp);
      const label = kind.shares > 1 ? `${kind.corp} ×${kind.shares}` : kind.corp;
      const effects: Effect[] = [
        {
          effect: "fly",
          from: [source, anchor.corp(kind.corp)],
          to: anchor.player(kind.player),
          label,
          certificate: { corpId: kind.corp, shares: kind.shares, president: kind.par !== undefined },
          color: color(kind.corp),
          durationMs: travel,
        },
        money([anchor.cash(kind.player), anchor.player(kind.player)], -kind.cost),
      ];
      if (kind.par !== undefined) {
        effects.push({ effect: "highlight", target: anchor.marketToken(kind.corp), color: color(kind.corp), durationMs: settle, delayMs: later });
      }
      if (kind.treasuryGain > 0) {
        effects.push(money([anchor.treasury(kind.corp), anchor.corp(kind.corp)], kind.treasuryGain, later));
      }
      return effects;
    }
    case "sell":
      return [
        {
          effect: "fly",
          from: anchor.player(kind.player),
          to: [anchor.pool(kind.corp), anchor.corp(kind.corp)],
          label: `${kind.corp} ×${kind.count}`,
          certificate: { corpId: kind.corp, shares: kind.count, president: false },
          color: color(kind.corp),
          durationMs: travel,
        },
        money([anchor.cash(kind.player), anchor.player(kind.player)], kind.proceeds, later),
        { effect: "highlight", target: anchor.marketToken(kind.corp), color: LOSS, durationMs: settle, delayMs: later },
      ];
    case "pass":
      return [
        { effect: "pop", at: anchor.player(kind.player), label: "Pass", durationMs: settle },
        ...kind.priceChanges.map(
          (change): Effect => ({ effect: "highlight", target: anchor.marketToken(change.corp), color: GAIN, durationMs: settle, delayMs: later }),
        ),
      ];
    case "chart":
    case "upgrade":
    case "service":
      return [
        { effect: "fly", from: [anchor.treasury(kind.corp), anchor.orderCorp(kind.corp), anchor.corp(kind.corp)], to: anchor.hex(kind.hex), label: signed(-kind.cost), variant: "coin", durationMs: travel },
        { effect: "highlight", target: anchor.hex(kind.hex), color: color(kind.corp), durationMs: settle, delayMs: later },
      ];
    case "no_action":
      return [{ effect: "pop", at: [anchor.orderCorp(kind.corp), anchor.corp(kind.corp)], label: "No action", durationMs: settle }];
    case "dividend": {
      const origin = [anchor.treasury(kind.corp), anchor.corp(kind.corp)];
      const holders = Object.entries(kind.payouts);
      const stagger = holders.length > 1 ? Math.round(later / (holders.length - 1)) : 0;
      const effects: Effect[] = holders.map(([playerId, amount], i) => ({
        effect: "fly",
        from: origin,
        to: [anchor.cash(playerId), anchor.player(playerId)],
        label: signed(amount),
        variant: "coin",
        durationMs: travel,
        delayMs: i * stagger,
      }));
      if (kind.treasuryGain > 0) effects.push(money(origin, kind.treasuryGain));
      if (kind.price.before !== kind.price.after) {
        const up = kind.price.after > kind.price.before;
        effects.push({ effect: "highlight", target: anchor.marketToken(kind.corp), color: up ? GAIN : LOSS, durationMs: settle, delayMs: later });
      }
      return effects;
    }
    case "phase":
    case "unknown":
      return [];
  }
}

/** Starts `step`'s effects. Effects whose anchors are not on screen do nothing. */
export function playEffects(step: PlaybackStep, flight: FlightApi, durationMs: number, color: (corpId: string) => string): void {
  for (const effect of effectsFor(step.kind, durationMs, color)) {
    if (effect.effect === "fly") void flight.fly(effect);
    else if (effect.effect === "pop") void flight.pop(effect);
    else void flight.highlight(effect);
  }
}
