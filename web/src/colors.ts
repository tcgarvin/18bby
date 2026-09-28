/** Corporation, region and planet-type palettes shared by the map and the side panels. */

import type { Region } from "./api";

const CORPORATION_COLORS: Record<string, string> = {
  CEC: "#1f5fa8",
  KDY: "#b5561b",
  CSC: "#7b3fa3",
  KTG: "#2d8a4e",
};

// Used only if the engine adds corporations this table does not know about yet.
const FALLBACK_COLORS = ["#c0392b", "#138d90", "#8a6d1f", "#5d6d7e"];

export function corporationColor(corpId: string, allIds: string[]): string {
  const known = CORPORATION_COLORS[corpId];
  if (known !== undefined) return known;
  const unknown = allIds.filter((id) => CORPORATION_COLORS[id] === undefined);
  return FALLBACK_COLORS[Math.max(0, unknown.indexOf(corpId)) % FALLBACK_COLORS.length];
}

export const REGION_FILL: Record<Region, string> = {
  Core: "#e7edf6",
  "Mid Rim": "#f2eee4",
  "Outer Rim": "#f8f9fa",
};

export const TAG_FILL: Record<string, string> = {
  A: "#d3ebd8",
  R: "#f8dac0",
  I: "#dfd9ef",
  S: "#cfe7e7",
  M: "#f1d6e1",
};

export const TAG_NAMES: Record<string, string> = {
  A: "Agriculture",
  R: "Resources",
  I: "Industry",
  S: "Shipyard",
  M: "Market",
};
