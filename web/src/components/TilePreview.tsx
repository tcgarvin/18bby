import type { DirectionName } from "../api";
import { cornersToPath, edgeMidpoint } from "../hex";

interface TilePreviewProps {
  /** Exits already on the tile, drawn as neutral lanes. */
  existing: DirectionName[];
  /** Exits the action adds, drawn in the corporation's color. */
  added: DirectionName[];
  color: string;
  size?: number;
}

const R = 20;

/** A small pointy-top hex showing a tile's lanes, used for choosing chart and upgrade options. */
export function TilePreview({ existing, added, color, size = 54 }: TilePreviewProps) {
  const lane = (exit: DirectionName, stroke: string, width: number) => {
    const mid = edgeMidpoint(exit, R);
    return <path key={`${exit}-${stroke}`} d={`M0,0L${mid.x.toFixed(2)},${mid.y.toFixed(2)}`} stroke={stroke} strokeWidth={width} strokeLinecap="round" />;
  };
  return (
    <svg width={size} height={size} viewBox={`${-R - 2} ${-R - 2} ${2 * R + 4} ${2 * R + 4}`} aria-hidden="true">
      <path d={cornersToPath({ x: 0, y: 0 }, R)} fill="#f4f6f9" stroke="#b7bfca" strokeWidth={1} />
      {existing.map((exit) => lane(exit, "#9aa3ae", 6))}
      {added.map((exit) => lane(exit, color, 5))}
      <circle r={2.6} fill={added.length ? color : "#9aa3ae"} />
    </svg>
  );
}
