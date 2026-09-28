import type { TileState } from "./api";
import { hexKey } from "./hex";

/**
 * Hexes whose tile differs between two states (new tile, new exit, or new service), each mapped
 * to the corporations that gained service there. The list is empty when only exits changed.
 */
export function changedHexes(before: TileState[], after: TileState[]): Map<string, string[]> {
  const previous = new Map(before.map((t) => [hexKey(t.hex), t] as const));
  const changed = new Map<string, string[]>();
  for (const tile of after) {
    const key = hexKey(tile.hex);
    const old = previous.get(key);
    const gained = tile.service.filter((corp) => !old?.service.includes(corp));
    const newExit = tile.exits.some((exit) => !old?.exits.includes(exit));
    if (!old || newExit || gained.length > 0) changed.set(key, gained);
  }
  return changed;
}
