import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type {
  Axial,
  Board,
  BuildFacilityAction,
  CorporationState,
  DeathStarState,
  DirectionName,
  FacilitiesState,
  FacilityState,
  HexAction,
  Planet,
  PlanetFacilities,
  Region,
  TerrainKind,
  TileState,
} from "../api";
import { EMPIRE } from "../api";
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
import { siteHexes, sitePlanet } from "../deathstar";
import { laneConnects, planetExitsText, planetsByKey as limitedPlanets } from "../facilities";
import { scatterBlobs } from "../terrain";
import { DeathStarShape } from "./DeathStar";
import "./HexMap.css";

/** Hex side length in SVG units; everything else on the map scales from it. */
const S = 34;
const LANE_WIDTH = S * 0.36;
const TRACE_WIDTH = S * 0.075;
const TRACE_SPACING = S * 0.082;
const BADGE_RADIUS = S * 0.36;
const NEUTRAL_CHANGE = "#5b6573";
const ASTEROID_ROCKS = { count: 9, area: S * 0.7, minRadius: 1.1, maxRadius: 3.1, salt: 1, overlap: false };
const NEBULA_WISPS = { count: 3, area: S * 0.75, minRadius: S * 0.22, maxRadius: S * 0.34, salt: 2, overlap: true };
/** Facility markers sit beside a planet's badge, at the corners between lanes (upper left, then lower left). */
const FACILITY_ANGLES = [210, 150];
const FACILITY_DISTANCE = BADGE_RADIUS + 8.5;
const FACILITY_SIZE = 10;
/** Open (unclaimed) exits show as small rings above the badge, where no lane can enter. */
const OPEN_EXIT_RADIUS = 3.2;
const OPEN_EXIT_SPACING = 8;
/** A dangling lane's bar sits this far along the lane from the planet's edge, clear of its name. */
const DANGLE_INSET = 0.24;

interface HexMapProps {
  board: Board;
  tiles: TileState[];
  /** Asteroid fields and nebulae by `hexKey`; plain space is absent. */
  terrain: Map<string, TerrainKind>;
  /** Extra cost to chart a nebula, quoted in its tooltip. */
  nebulaChartSurcharge: number;
  corporations: CorporationState[];
  /** Corporation whose network is emphasized, or null for the neutral overview. */
  focusCorp: string | null;
  /** Hexes with at least one legal network action for the acting corporation. Asteroid fields are never drawn as targets. */
  actionableHexes: Set<string>;
  selectedHex: Axial | null;
  preview: HexAction | null;
  /** Hexes changed by others since your move, with the corporations that gained service there. */
  changedHexes: Map<string, string[]>;
  onHexClick: (hex: Axial) => void;
  /** Zoom to these hexes (with a margin) instead of showing the whole board. */
  fitHexes?: Axial[];
  /** Accessible name for the map. */
  label?: string;
  /** The Death Star track and sites, under those rules: the active site is drawn as a hub. */
  deathStar?: DeathStarState;
  /**
   * Planet exits and facilities, under the facility rules: lanes run into a planet only through a
   * claimed exit, lanes facing it without one are marked as dangling, and its open exits and
   * facilities are drawn beside it.
   */
  facilities?: Pick<FacilitiesState, "planets">;
  /** A facility build to preview in the focused corporation's colour: the facility and its new exit's lane. */
  facilityPreview?: BuildFacilityAction | null;
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

/** Whether a lane facing the planet at a hex key from one of its sides runs into it. */
type Connects = (planetKey: string, side: DirectionName) => boolean;

const OPEN_HUBS: Connects = () => true;

/** The stub from a planet's edge on `side` into its badge. */
function stubPoints(planetHex: Axial, side: DirectionName): { from: Point; to: Point } {
  const planetCenter = hexToPixel(planetHex, S);
  const outward = edgeMidpoint(side, S);
  const length = Math.hypot(outward.x, outward.y);
  return { from: add(planetCenter, outward), to: add(planetCenter, outward, BADGE_RADIUS / length) };
}

/**
 * Lane segments for charted tiles: one per exit from the tile center to the edge midpoint,
 * plus a stub into any planet the exit faces that it `connects` into (every planet, while they
 * are open hubs; under the facility rules only through a claimed exit).
 */
function buildSegments(tiles: TileState[], planetsByKey: Map<string, Planet>, connects: Connects = OPEN_HUBS): Segment[] {
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
      const side = oppositeOf(exit);
      if (planetsByKey.has(hexKey(facing)) && connects(hexKey(facing), side)) {
        segments.push({ key: `${hexKey(tile.hex)}:${exit}:stub`, ...stubPoints(facing, side), normal, service: tile.service });
      }
    }
  }
  return segments;
}

/** A lane that faces an exit-limited planet without an exit there (facility rules). */
interface DanglingEnd {
  key: string;
  planet: PlanetFacilities;
  side: DirectionName;
  /** Where the lane meets the planet's hex. */
  at: Point;
  /** Unit vector across the lane at its end. */
  across: Point;
}

function danglingEnds(planets: PlanetFacilities[]): DanglingEnd[] {
  return planets.flatMap((planet) =>
    planet.dangling.map((side) => {
      const center = hexToPixel(planet.hex, S);
      const mid = edgeMidpoint(side, S);
      const length = Math.hypot(mid.x, mid.y);
      return {
        key: `${hexKey(planet.hex)}:${side}`,
        planet,
        side,
        at: add(center, mid, 1 + DANGLE_INSET),
        across: { x: -mid.y / length, y: mid.x / length },
      };
    }),
  );
}

/** Offset of facility marker `index` from its planet's centre. */
function facilitySpot(index: number): Point {
  const radians = (FACILITY_ANGLES[index % FACILITY_ANGLES.length] * Math.PI) / 180;
  const ring = FACILITY_DISTANCE + Math.floor(index / FACILITY_ANGLES.length) * FACILITY_SIZE;
  return { x: ring * Math.cos(radians), y: ring * Math.sin(radians) };
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

/** The smallest number of hex rows a zoomed map shows, so a one-planet network keeps context. */
const MIN_FIT_SPAN = S * 9;

function viewBox(hexes: Axial[], minSpan = 0): string {
  const points = hexes.map((h) => hexToPixel(h, S));
  const pad = S * 1.3;
  let minX = Math.min(...points.map((p) => p.x)) - pad;
  let maxX = Math.max(...points.map((p) => p.x)) + pad;
  let minY = Math.min(...points.map((p) => p.y)) - pad;
  let maxY = Math.max(...points.map((p) => p.y)) + pad;
  const grow = (low: number, high: number): [number, number] => {
    const extra = Math.max(0, minSpan - (high - low)) / 2;
    return [low - extra, high + extra];
  };
  [minX, maxX] = grow(minX, maxX);
  [minY, maxY] = grow(minY, maxY);
  return `${minX.toFixed(1)} ${minY.toFixed(1)} ${(maxX - minX).toFixed(1)} ${(maxY - minY).toFixed(1)}`;
}

const NO_KEYS = new Set<string>();

/**
 * Keys that appeared in `keys` since it last changed (none on the first render), for drawing
 * newly built lanes in. They stay fresh until `keys` changes again, so re-renders in between
 * do not cut the animation short.
 */
function useFreshKeys(keys: string[]): Set<string> {
  const previous = useRef<Set<string> | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(NO_KEYS);
  const signature = keys.join("|");
  useLayoutEffect(() => {
    const before = previous.current;
    previous.current = new Set(keys);
    if (before === null) return;
    const added = keys.filter((key) => !before.has(key));
    setFresh(added.length > 0 ? new Set(added) : NO_KEYS);
    // `signature` stands in for `keys`, which is rebuilt on every render.
  }, [signature]);
  return fresh;
}

function line(from: Point, to: Point): string {
  return `M${from.x.toFixed(2)},${from.y.toFixed(2)}L${to.x.toFixed(2)},${to.y.toFixed(2)}`;
}

/**
 * Segments that the preview action would add or give service on. A new exit facing an
 * exit-limited planet claims an open exit there if it has one (`claims`); service claims nothing.
 */
function previewSegments(
  preview: HexAction,
  tiles: TileState[],
  planetsByKey: Map<string, Planet>,
  corp: string,
  connects: Connects,
  claims: Connects,
): Segment[] {
  const existing = tiles.find((t) => hexKey(t.hex) === hexKey(preview.hex));
  let exits: DirectionName[];
  if (preview.type === "chart") exits = preview.exits;
  else if (preview.type === "upgrade") exits = [preview.exit];
  else exits = existing?.exits ?? [];
  return buildSegments([{ hex: preview.hex, exits, service: [corp] }], planetsByKey, preview.type === "service" ? connects : claims);
}

export function HexMap(props: HexMapProps) {
  const {
    board,
    tiles,
    terrain,
    nebulaChartSurcharge,
    corporations,
    focusCorp,
    actionableHexes,
    selectedHex,
    preview,
    changedHexes,
    onHexClick,
    fitHexes,
    label = "Galaxy map",
    deathStar,
    facilities,
    facilityPreview = null,
  } = props;
  const corpIds = useMemo(() => corporations.map((c) => c.id), [corporations]);
  const regions = useMemo(() => assignRegions(board.hexes, board.planets), [board]);
  const boundaries = useMemo(() => regionBoundaries(board, regions), [board, regions]);
  const fitKey = fitHexes ? fitHexes.map(hexKey).join(" ") : "";
  const box = useMemo(
    () => (fitHexes && fitHexes.length > 0 ? viewBox(fitHexes, MIN_FIT_SPAN) : viewBox(board.hexes)),
    // fitKey stands in for fitHexes, which callers rebuild on every render.
    [board, fitKey],
  );
  // The construction site is a hub like a planet (lanes stub into it, pairs arc to it), but region
  // shading stays with the real planets, as on the server.
  const site = sitePlanet(deathStar);
  const siteKey = site ? `${site.name}@${hexKey(site.hex)}` : "";
  const hubs = useMemo(() => (site ? [...board.planets, site] : board.planets), [board, siteKey]);
  const reservedKey = siteHexes(deathStar, "reserved").map(hexKey).join(" ");
  const reserved = useMemo(() => siteHexes(deathStar, "reserved"), [reservedKey]);
  const planetsByKey = useMemo(() => new Map(hubs.map((p) => [hexKey(p.hex), p] as const)), [hubs]);
  const planetsByName = useMemo(() => new Map(hubs.map((p) => [p.name, p] as const)), [hubs]);
  // Under the facility rules planets have limited exits; without them every planet is an open hub.
  const limited = useMemo(() => limitedPlanets(facilities), [facilities]);
  const connects = useMemo<Connects>(() => (key, side) => laneConnects(limited, key, side), [limited]);
  const claims = useMemo<Connects>(
    () => (key, side) => laneConnects(limited, key, side) || (limited.get(key)?.unclaimed ?? 0) > 0,
    [limited],
  );
  const segments = useMemo(() => buildSegments(tiles, planetsByKey, connects), [tiles, planetsByKey, connects]);
  const dangling = useMemo(() => danglingEnds(facilities?.planets ?? []), [facilities]);
  const builtKeys = useMemo(
    () => segments.flatMap((seg) => [seg.key, ...seg.service.map((corpId) => `${seg.key}:${corpId}`)]),
    [segments],
  );
  const fresh = useFreshKeys(builtKeys);
  // A facility is new when its build number, or its owner (a seizure), was not on the map before.
  const facilityKeys = useMemo(
    () => (facilities?.planets ?? []).flatMap((p) => p.facilities.map((f) => facilityKey(p, f))),
    [facilities],
  );
  const freshFacilities = useFreshKeys(facilityKeys);
  const terrainCells = useMemo(
    () =>
      board.hexes.flatMap((hex) => {
        const kind = terrain.get(hexKey(hex));
        return kind === undefined ? [] : [<TerrainCell key={hexKey(hex)} hex={hex} kind={kind} surcharge={nebulaChartSurcharge} />];
      }),
    [board, terrain, nebulaChartSurcharge],
  );
  // The engine never offers actions on an asteroid field; filtering here keeps one from being drawn or clicked regardless.
  const targetHexes = board.hexes.filter((hex) => actionableHexes.has(hexKey(hex)) && terrain.get(hexKey(hex)) !== "asteroid");

  const focus = corporations.find((c) => c.id === focusCorp) ?? null;
  const reachable = new Set(focus?.reachablePlanets ?? []);
  const slotOffset = (corpId: string): number =>
    (corpIds.indexOf(corpId) - (corpIds.length - 1) / 2) * TRACE_SPACING;
  const homeworlds = new Map<string, CorporationState[]>();
  for (const corp of corporations) {
    homeworlds.set(corp.homeworld, [...(homeworlds.get(corp.homeworld) ?? []), corp]);
  }

  return (
    <svg className={`hexmap${focus ? " hexmap--focused" : ""}`} viewBox={box} role="img" aria-label={label}>
      <defs>
        <radialGradient id="hexmap-nebula-haze">
          <stop offset="0%" className="hexmap__haze-core" />
          <stop offset="100%" className="hexmap__haze-edge" />
        </radialGradient>
        <radialGradient id="hexmap-nebula-wisp">
          <stop offset="0%" className="hexmap__wisp-core" />
          <stop offset="100%" className="hexmap__wisp-edge" />
        </radialGradient>
      </defs>
      <g className="hexmap__cells">
        {board.hexes.map((hex) => {
          const region = regions.get(hexKey(hex)) ?? "Outer Rim";
          return (
            <path
              key={hexKey(hex)}
              data-hex={hexKey(hex)}
              d={cornersToPath(hexToPixel(hex, S), S)}
              fill={REGION_FILL[region]}
              className="hexmap__cell"
            />
          );
        })}
      </g>
      <g className="hexmap__terrain">{terrainCells}</g>
      <path d={boundaries} className="hexmap__boundary" />

      <g className="hexmap__actionable">
        {targetHexes.map((hex) => {
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
          <path
            key={seg.key}
            d={line(seg.from, seg.to)}
            strokeWidth={LANE_WIDTH}
            className={`hexmap__lane${fresh.has(seg.key) ? " hexmap__lane--fresh" : ""}`}
            pathLength={fresh.has(seg.key) ? 1 : undefined}
          />
        ))}
      </g>

      <g className="hexmap__traces">
        {/* A glow in the builder's colour behind lanes and service that just appeared. */}
        {segments.flatMap((seg) =>
          seg.service
            .filter((corpId) => fresh.has(`${seg.key}:${corpId}`))
            .map((corpId) => (
              <path
                key={`${seg.key}:${corpId}:glow`}
                d={line(seg.from, seg.to)}
                stroke={corporationColor(corpId, corpIds)}
                strokeWidth={LANE_WIDTH * 1.5}
                className="hexmap__glow"
              />
            )),
        )}
        {segments.flatMap((seg) =>
          seg.service.map((corpId) => {
            const key = `${seg.key}:${corpId}`;
            const offset = slotOffset(corpId);
            const dimmed = focus !== null && corpId !== focus.id;
            const isFresh = fresh.has(key);
            return (
              <path
                key={key}
                d={line(add(seg.from, seg.normal, offset), add(seg.to, seg.normal, offset))}
                stroke={corporationColor(corpId, corpIds)}
                strokeWidth={focus?.id === corpId ? TRACE_WIDTH * 1.35 : TRACE_WIDTH}
                className={`hexmap__trace${dimmed ? " hexmap__trace--dimmed" : ""}${isFresh ? " hexmap__trace--fresh" : ""}`}
                pathLength={isFresh ? 1 : undefined}
              />
            );
          }),
        )}
      </g>

      <g className="hexmap__changes">
        {board.hexes
          .filter((hex) => changedHexes.has(hexKey(hex)))
          .map((hex) => {
            const gained = changedHexes.get(hexKey(hex)) ?? [];
            return (
              <path
                key={hexKey(hex)}
                d={cornersToPath(hexToPixel(hex, S), S * 0.94)}
                stroke={gained.length > 0 ? corporationColor(gained[0], corpIds) : NEUTRAL_CHANGE}
                className="hexmap__change"
              >
                <title>
                  {limited.has(hexKey(hex))
                    ? gained.length > 0
                      ? `New facility: ${gained.join(", ")}`
                      : "Facility taken over by the Empire"
                    : gained.length > 0
                      ? `New service: ${gained.join(", ")}`
                      : "New exit"}
                </title>
              </path>
            );
          })}
      </g>

      {preview && focus && (
        <g className="hexmap__preview">
          {previewSegments(preview, tiles, planetsByKey, focus.id, connects, claims).map((seg) => (
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
                  className={`hexmap__pair${pair.contract ? " hexmap__pair--contract" : pair.typed ? "" : " hexmap__pair--basic"}`}
                />
                <g transform={`translate(${labelAt.x},${labelAt.y})`} className={pair.contract ? "hexmap__pair-label--contract" : undefined}>
                  {pair.contract && <title>{`Contract ${pair.a} ↔ ${pair.b}: ${pair.value}, and a cube on the Death Star track`}</title>}
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

      {reserved.length > 0 && (
        <g className="hexmap__reserved">
          {reserved.map((hex) => {
            const center = hexToPixel(hex, S);
            return (
              <g key={hexKey(hex)}>
                <title>
                  Future Death Star site: the construction moves here when its site-move stage fills. Until then it
                  cannot be charted, but lanes may point at it.
                </title>
                <path d={cornersToPath(center, S * 0.86)} className="hexmap__reserved-hex" />
                <circle cx={center.x} cy={center.y} r={BADGE_RADIUS} className="hexmap__reserved-dot" />
                <text x={center.x} y={center.y + BADGE_RADIUS + 12} className="hexmap__reserved-label">
                  future site
                </text>
              </g>
            );
          })}
        </g>
      )}

      {site && deathStar && (
        <g
          transform={`translate(${hexToPixel(site.hex, S).x},${hexToPixel(site.hex, S).y})`}
          className={`hexmap__planet hexmap__site${focus !== null && !reachable.has(site.name) ? " hexmap__planet--dimmed" : ""}`}
        >
          <title>{`${site.name} construction site · ${site.region} · ${deathStar.siteTag} (Imperial Works): an open hub. Paired with ${deathStar.contractPartnerTags.join(", ")} it is a contract worth ${deathStar.contractValue}.`}</title>
          {focus !== null && reachable.has(site.name) && (
            <circle r={BADGE_RADIUS + 4} fill="none" stroke={corporationColor(focus.id, corpIds)} strokeWidth={2.5} />
          )}
          <DeathStarShape r={BADGE_RADIUS} />
          <g transform={`translate(${BADGE_RADIUS * 0.8},${BADGE_RADIUS * 0.8})`}>
            <circle r={6} className="hexmap__site-tag" />
            <text className="hexmap__site-tag-text" dy="0.35em">
              {deathStar.siteTag}
            </text>
          </g>
          <text className="hexmap__planet-name" y={BADGE_RADIUS + 12}>
            {site.name}
          </text>
        </g>
      )}

      <g className="hexmap__planets">
        {board.planets.map((planet) => {
          const center = hexToPixel(planet.hex, S);
          const dimmed = focus !== null && !reachable.has(planet.name);
          const reached = focus !== null && reachable.has(planet.name);
          const homes = homeworlds.get(planet.name) ?? [];
          const exits = limited.get(hexKey(planet.hex));
          return (
            <g
              key={planet.name}
              transform={`translate(${center.x},${center.y})`}
              className={`hexmap__planet${dimmed ? " hexmap__planet--dimmed" : ""}`}
            >
              <title>{`${planet.name} · ${planet.region} · ${badgeText(planet.tags)}${exits ? ` · ${planetExitsText(exits)}` : ""}`}</title>
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
              {exits && <OpenExits count={exits.unclaimed} />}
              {exits?.facilities.map((facility, i) => (
                <FacilityMarker
                  key={facility.build}
                  facility={facility}
                  at={facilitySpot(i)}
                  color={facility.owner === EMPIRE ? "" : corporationColor(facility.owner, corpIds)}
                  fresh={freshFacilities.has(facilityKey(exits, facility))}
                />
              ))}
            </g>
          );
        })}
      </g>

      {dangling.length > 0 && (
        <g className="hexmap__dangling">
          {dangling.map((end) => {
            const half = LANE_WIDTH * 0.62;
            return (
              <path
                key={end.key}
                d={line(add(end.at, end.across, -half), add(end.at, end.across, half))}
                className="hexmap__dangle"
              >
                <title>{`Dangling lane: ${end.planet.name} has no exit on this side, so the lane does not connect. A facility built there can give it the new exit.`}</title>
              </path>
            );
          })}
        </g>
      )}

      {facilityPreview && focus && (
        <FacilityPreview
          action={facilityPreview}
          planet={limited.get(hexKey(facilityPreview.planet))}
          color={corporationColor(focus.id, corpIds)}
        />
      )}

      <g className="hexmap__targets">
        {targetHexes.map((hex) => (
          <path
            key={hexKey(hex)}
            d={cornersToPath(hexToPixel(hex, S), S)}
            className="hexmap__target"
            onClick={() => onHexClick(hex)}
          >
            <title>
              {limited.has(hexKey(hex))
                ? `${limited.get(hexKey(hex))?.name}: facility options`
                : `Hex (${hex[0]}, ${hex[1]}): network options${terrain.get(hexKey(hex)) === "nebula" ? " · nebula" : ""}`}
            </title>
          </path>
        ))}
      </g>
    </svg>
  );
}

/** An asteroid field (dark, studded with rocks) or a nebula (a purple and pink haze) filling one hex. */
function TerrainCell({ hex, kind, surcharge }: { hex: Axial; kind: TerrainKind; surcharge: number }) {
  const center = hexToPixel(hex, S);
  const outline = cornersToPath(center, S);
  if (kind === "asteroid") {
    return (
      <g>
        <title>Asteroid field: impassable. It cannot be charted, and no lane may face it.</title>
        <path d={outline} className="hexmap__asteroid" />
        {scatterBlobs(hex, ASTEROID_ROCKS).map((rock, i) => (
          <circle key={i} cx={center.x + rock.x} cy={center.y + rock.y} r={rock.r} className={`hexmap__rock hexmap__rock--${i % 3}`} />
        ))}
      </g>
    );
  }
  return (
    <g>
      <title>{`Nebula: charting costs ${surcharge} more, and its tile can never gain a third exit.`}</title>
      <path d={outline} className="hexmap__nebula" />
      {scatterBlobs(hex, NEBULA_WISPS).map((wisp, i) => (
        <circle key={i} cx={center.x + wisp.x} cy={center.y + wisp.y} r={wisp.r} className="hexmap__wisp" />
      ))}
    </g>
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

function facilityKey(planet: PlanetFacilities, facility: FacilityState): string {
  return `${hexKey(planet.hex)}:${facility.build}:${facility.owner}`;
}

/** A planet's unclaimed exits, as small open rings above its badge (facility rules). */
function OpenExits({ count }: { count: number }) {
  if (count <= 0) return null;
  const y = -BADGE_RADIUS - OPEN_EXIT_RADIUS - 3;
  return (
    <g className="hexmap__open-exits">
      {Array.from({ length: count }, (_, i) => (
        <circle key={i} cx={(i - (count - 1) / 2) * OPEN_EXIT_SPACING} cy={y} r={OPEN_EXIT_RADIUS} className="hexmap__open-exit" />
      ))}
    </g>
  );
}

/**
 * One facility beside its planet: a square in its corporation's colour, or for an Imperial one
 * (`color` empty) a diamond in the Empire's.
 */
function FacilityMarker({ facility, at, color, fresh }: { facility: FacilityState; at: Point; color: string; fresh: boolean }) {
  const half = FACILITY_SIZE / 2;
  const imperial = facility.owner === EMPIRE;
  return (
    <g transform={`translate(${at.x.toFixed(2)},${at.y.toFixed(2)})`}>
      <g className={`hexmap__facility${imperial ? " hexmap__facility--imperial" : ""}${fresh ? " hexmap__facility--fresh" : ""}`}>
        <title>
          {imperial
            ? "Imperial facility: it fills a slot and keeps its exit, but runs pairs for nobody"
            : `${facility.owner} facility: one revenue pair for ${facility.owner}, and an exit for this planet`}
        </title>
        {imperial ? (
          <>
            <path d={`M0,${-half - 1}L${half + 1},0L0,${half + 1}L${-half - 1},0Z`} className="hexmap__facility-body" />
            <circle r={1.5} className="hexmap__facility-dot" />
          </>
        ) : (
          <rect x={-half} y={-half} width={FACILITY_SIZE} height={FACILITY_SIZE} rx={1.6} fill={color} className="hexmap__facility-body" />
        )}
      </g>
    </g>
  );
}

/** The facility a build would add, and the stub of the lane its new exit would connect, in the builder's colour. */
function FacilityPreview({ action, planet, color }: { action: BuildFacilityAction; planet: PlanetFacilities | undefined; color: string }) {
  const center = hexToPixel(action.planet, S);
  const spot = facilitySpot(planet?.facilities.length ?? 0);
  const half = FACILITY_SIZE / 2;
  const stub = action.exit ? stubPoints(action.planet, action.exit) : null;
  return (
    <g className="hexmap__facility-preview">
      {stub && (
        <>
          <path d={line(stub.from, stub.to)} stroke={color} strokeWidth={LANE_WIDTH * 0.7} />
          <circle cx={stub.from.x} cy={stub.from.y} r={LANE_WIDTH * 0.75} stroke={color} className="hexmap__facility-preview-ring" />
        </>
      )}
      <rect
        x={center.x + spot.x - half}
        y={center.y + spot.y - half}
        width={FACILITY_SIZE}
        height={FACILITY_SIZE}
        rx={1.6}
        fill={color}
        stroke={color}
      />
    </g>
  );
}
