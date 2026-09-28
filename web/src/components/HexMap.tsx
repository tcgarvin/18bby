import { useMemo } from "react";
import type { Axial, Board, CorporationState, DirectionName, HexAction, Planet, Region, TileState } from "../api";
import { REGION_FILL, TAG_FILL, corporationColor } from "../colors";
import {
  DIRECTIONS,
  assignRegions,
  badgeText,
  cornersToPath,
  edgeEndpoints,
  edgeMidpoint,
  hexKey,
  hexToPixel,
  neighbor,
  type Point,
} from "../hex";
import "./HexMap.css";

/** Hex side length in SVG units; everything else on the map scales from it. */
const S = 34;
const LANE_WIDTH = S * 0.36;
const TRACE_WIDTH = S * 0.075;
const TRACE_SPACING = S * 0.082;
const BADGE_RADIUS = S * 0.36;

interface HexMapProps {
  board: Board;
  tiles: TileState[];
  corporations: CorporationState[];
  /** Corporation whose network is emphasized, or null for the neutral overview. */
  focusCorp: string | null;
  /** Hexes with at least one legal network action for the acting corporation. */
  actionableHexes: Set<string>;
  selectedHex: Axial | null;
  preview: HexAction | null;
  onHexClick: (hex: Axial) => void;
}

interface Segment {
  key: string;
  from: Point;
  to: Point;
  /** Canonical unit normal so a trace keeps the same side across the shared edge. */
  normal: Point;
  service: string[];
}

function oppositeOf(direction: DirectionName): DirectionName {
  return DIRECTIONS[(DIRECTIONS.indexOf(direction) + 3) % 6];
}

function canonicalNormal(direction: DirectionName): Point {
  const index = DIRECTIONS.indexOf(direction);
  const base = index < 3 ? direction : oppositeOf(direction);
  const mid = edgeMidpoint(base, 1);
  const length = Math.hypot(mid.x, mid.y);
  return { x: -mid.y / length, y: mid.x / length };
}

function add(a: Point, b: Point, scale = 1): Point {
  return { x: a.x + b.x * scale, y: a.y + b.y * scale };
}

/**
 * Lane segments for charted tiles: one per exit from the tile center to the edge midpoint,
 * plus a stub into any planet the exit faces (planets are open hubs with every exit).
 */
function buildSegments(tiles: TileState[], planetsByKey: Map<string, Planet>): Segment[] {
  const segments: Segment[] = [];
  for (const tile of tiles) {
    const center = hexToPixel(tile.hex, S);
    for (const exit of tile.exits) {
      const normal = canonicalNormal(exit);
      segments.push({
        key: `${hexKey(tile.hex)}:${exit}`,
        from: center,
        to: add(center, edgeMidpoint(exit, S)),
        normal,
        service: tile.service,
      });
      const facing = neighbor(tile.hex, exit);
      if (planetsByKey.has(hexKey(facing))) {
        const planetCenter = hexToPixel(facing, S);
        const inward = edgeMidpoint(oppositeOf(exit), S);
        const length = Math.hypot(inward.x, inward.y);
        segments.push({
          key: `${hexKey(tile.hex)}:${exit}:stub`,
          from: add(planetCenter, inward),
          to: add(planetCenter, inward, BADGE_RADIUS / length),
          normal,
          service: tile.service,
        });
      }
    }
  }
  return segments;
}

function regionBoundaries(board: Board, regions: Map<string, Region>): string {
  const parts: string[] = [];
  for (const hex of board.hexes) {
    const region = regions.get(hexKey(hex));
    const center = hexToPixel(hex, S);
    // Only three directions, so each shared edge is drawn once.
    for (const direction of ["E", "SE", "SW"] as DirectionName[]) {
      const other = regions.get(hexKey(neighbor(hex, direction)));
      if (other === undefined || other === region) continue;
      const [a, b] = edgeEndpoints(direction, S);
      parts.push(
        `M${(center.x + a.x).toFixed(2)},${(center.y + a.y).toFixed(2)}L${(center.x + b.x).toFixed(2)},${(center.y + b.y).toFixed(2)}`,
      );
    }
  }
  return parts.join("");
}

function viewBox(board: Board): string {
  const points = board.hexes.map((h) => hexToPixel(h, S));
  const pad = S * 1.3;
  const minX = Math.min(...points.map((p) => p.x)) - pad;
  const maxX = Math.max(...points.map((p) => p.x)) + pad;
  const minY = Math.min(...points.map((p) => p.y)) - pad;
  const maxY = Math.max(...points.map((p) => p.y)) + pad;
  return `${minX.toFixed(1)} ${minY.toFixed(1)} ${(maxX - minX).toFixed(1)} ${(maxY - minY).toFixed(1)}`;
}

function line(from: Point, to: Point): string {
  return `M${from.x.toFixed(2)},${from.y.toFixed(2)}L${to.x.toFixed(2)},${to.y.toFixed(2)}`;
}

/** Segments that the preview action would add or give service on. */
function previewSegments(preview: HexAction, tiles: TileState[], planetsByKey: Map<string, Planet>, corp: string): Segment[] {
  const existing = tiles.find((t) => hexKey(t.hex) === hexKey(preview.hex));
  let exits: DirectionName[];
  if (preview.type === "chart") exits = preview.exits;
  else if (preview.type === "upgrade") exits = [preview.exit];
  else exits = existing?.exits ?? [];
  return buildSegments([{ hex: preview.hex, exits, service: [corp] }], planetsByKey);
}

export function HexMap(props: HexMapProps) {
  const { board, tiles, corporations, focusCorp, actionableHexes, selectedHex, preview, onHexClick } = props;
  const corpIds = useMemo(() => corporations.map((c) => c.id), [corporations]);
  const regions = useMemo(() => assignRegions(board.hexes, board.planets), [board]);
  const boundaries = useMemo(() => regionBoundaries(board, regions), [board, regions]);
  const box = useMemo(() => viewBox(board), [board]);
  const planetsByKey = useMemo(
    () => new Map(board.planets.map((p) => [hexKey(p.hex), p] as const)),
    [board],
  );
  const planetsByName = useMemo(() => new Map(board.planets.map((p) => [p.name, p] as const)), [board]);
  const segments = useMemo(() => buildSegments(tiles, planetsByKey), [tiles, planetsByKey]);

  const focus = corporations.find((c) => c.id === focusCorp) ?? null;
  const reachable = new Set(focus?.reachablePlanets ?? []);
  const slotOffset = (corpId: string): number =>
    (corpIds.indexOf(corpId) - (corpIds.length - 1) / 2) * TRACE_SPACING;
  const homeworlds = new Map<string, CorporationState[]>();
  for (const corp of corporations) {
    homeworlds.set(corp.homeworld, [...(homeworlds.get(corp.homeworld) ?? []), corp]);
  }

  return (
    <svg className={`hexmap${focus ? " hexmap--focused" : ""}`} viewBox={box} role="img" aria-label="Galaxy map">
      <g className="hexmap__cells">
        {board.hexes.map((hex) => {
          const region = regions.get(hexKey(hex)) ?? "Outer Rim";
          return (
            <path key={hexKey(hex)} d={cornersToPath(hexToPixel(hex, S), S)} fill={REGION_FILL[region]} className="hexmap__cell" />
          );
        })}
      </g>
      <path d={boundaries} className="hexmap__boundary" />

      <g className="hexmap__actionable">
        {board.hexes
          .filter((hex) => actionableHexes.has(hexKey(hex)))
          .map((hex) => {
            const selected = selectedHex !== null && hexKey(selectedHex) === hexKey(hex);
            return (
              <path
                key={hexKey(hex)}
                d={cornersToPath(hexToPixel(hex, S), S * 0.9)}
                className={`hexmap__option${selected ? " hexmap__option--selected" : ""}`}
              />
            );
          })}
      </g>

      <g className="hexmap__lanes">
        {segments.map((seg) => (
          <path key={seg.key} d={line(seg.from, seg.to)} strokeWidth={LANE_WIDTH} className="hexmap__lane" />
        ))}
      </g>

      <g className="hexmap__traces">
        {segments.flatMap((seg) =>
          seg.service.map((corpId) => {
            const offset = slotOffset(corpId);
            const dimmed = focus !== null && corpId !== focus.id;
            return (
              <path
                key={`${seg.key}:${corpId}`}
                d={line(add(seg.from, seg.normal, offset), add(seg.to, seg.normal, offset))}
                stroke={corporationColor(corpId, corpIds)}
                strokeWidth={focus?.id === corpId ? TRACE_WIDTH * 1.35 : TRACE_WIDTH}
                className={`hexmap__trace${dimmed ? " hexmap__trace--dimmed" : ""}`}
              />
            );
          }),
        )}
      </g>

      {preview && focus && (
        <g className="hexmap__preview">
          {previewSegments(preview, tiles, planetsByKey, focus.id).map((seg) => (
            <path
              key={seg.key}
              d={line(seg.from, seg.to)}
              stroke={corporationColor(focus.id, corpIds)}
              strokeWidth={LANE_WIDTH * 0.7}
            />
          ))}
        </g>
      )}

      {focus && (
        <g className="hexmap__pairs">
          {focus.revenue.pairs.map((pair) => {
            const a = planetsByName.get(pair.a);
            const b = planetsByName.get(pair.b);
            if (!a || !b) return null;
            const pa = hexToPixel(a.hex, S);
            const pb = hexToPixel(b.hex, S);
            const mid = { x: (pa.x + pb.x) / 2, y: (pa.y + pb.y) / 2 };
            const length = Math.hypot(pb.x - pa.x, pb.y - pa.y) || 1;
            const bow = Math.min(S * 1.2, length * 0.18);
            const control = { x: mid.x - ((pb.y - pa.y) / length) * bow, y: mid.y + ((pb.x - pa.x) / length) * bow };
            const labelAt = { x: (mid.x + control.x) / 2, y: (mid.y + control.y) / 2 };
            return (
              <g key={`${pair.a}-${pair.b}`}>
                <path
                  d={`M${pa.x},${pa.y}Q${control.x},${control.y} ${pb.x},${pb.y}`}
                  stroke={corporationColor(focus.id, corpIds)}
                  className={`hexmap__pair${pair.typed ? "" : " hexmap__pair--basic"}`}
                />
                <g transform={`translate(${labelAt.x},${labelAt.y})`}>
                  <rect x={-13} y={-8} width={26} height={16} rx={8} className="hexmap__pair-pill" stroke={corporationColor(focus.id, corpIds)} />
                  <text className="hexmap__pair-value" dy="0.35em">
                    {pair.value}
                  </text>
                </g>
              </g>
            );
          })}
        </g>
      )}

      <g className="hexmap__planets">
        {board.planets.map((planet) => {
          const center = hexToPixel(planet.hex, S);
          const dimmed = focus !== null && !reachable.has(planet.name);
          const reached = focus !== null && reachable.has(planet.name);
          const homes = homeworlds.get(planet.name) ?? [];
          return (
            <g
              key={planet.name}
              transform={`translate(${center.x},${center.y})`}
              className={`hexmap__planet${dimmed ? " hexmap__planet--dimmed" : ""}`}
            >
              <title>{`${planet.name} · ${planet.region} · ${badgeText(planet.tags)}`}</title>
              {reached && focus && (
                <circle r={BADGE_RADIUS + 4} fill="none" stroke={corporationColor(focus.id, corpIds)} strokeWidth={2.5} />
              )}
              <PlanetBadge tags={planet.tags} />
              <text className="hexmap__planet-name" y={BADGE_RADIUS + 12}>
                {planet.name}
              </text>
              {homes.map((corp, i) => (
                <g key={corp.id} transform={`translate(${BADGE_RADIUS + 2},${-BADGE_RADIUS - 6 + i * 13})`}>
                  <rect width={24} height={11} rx={2} fill={corporationColor(corp.id, corpIds)} />
                  <text x={12} y={8.3} className="hexmap__home-label">
                    {corp.id}
                  </text>
                </g>
              ))}
            </g>
          );
        })}
      </g>

      <g className="hexmap__targets">
        {board.hexes
          .filter((hex) => actionableHexes.has(hexKey(hex)))
          .map((hex) => (
            <path
              key={hexKey(hex)}
              d={cornersToPath(hexToPixel(hex, S), S)}
              className="hexmap__target"
              onClick={() => onHexClick(hex)}
            >
              <title>{`Hex (${hex[0]}, ${hex[1]}): network options`}</title>
            </path>
          ))}
      </g>
    </svg>
  );
}

function PlanetBadge({ tags }: { tags: string[] }) {
  const r = BADGE_RADIUS;
  const text = badgeText(tags);
  return (
    <g className="hexmap__badge">
      {tags.length === 2 ? (
        <>
          <path d={`M0,${-r}A${r},${r} 0 0 0 0,${r}Z`} fill={TAG_FILL[tags[0]] ?? "#eee"} />
          <path d={`M0,${-r}A${r},${r} 0 0 1 0,${r}Z`} fill={TAG_FILL[tags[1]] ?? "#eee"} />
          <circle r={r} fill="none" className="hexmap__badge-ring" />
        </>
      ) : (
        <circle r={r} fill={TAG_FILL[tags[0]] ?? "#eee"} className="hexmap__badge-ring" />
      )}
      <text className={`hexmap__badge-text${text.length > 1 ? " hexmap__badge-text--dual" : ""}`} dy="0.35em">
        {text}
      </text>
    </g>
  );
}
