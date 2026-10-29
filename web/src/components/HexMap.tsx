import { useId, useLayoutEffect, useMemo, useRef, useState } from "react";
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
import { slotOffset, solveLaneOrder, type LaneOrder } from "../laneOrder";
import {
  apothem,
  branchTrace,
  oppositeOf,
  piecePath,
  portEnd,
  stubPiece,
  tileRoute,
  tracePath,
  trunkPiece,
  type LanePiece,
} from "../lanes";
import { scatterBlobs } from "../terrain";
import { DeathStarShape } from "./DeathStar";
import "./HexMap.css";

/** Hex side length in SVG units; everything else on the map scales from it. */
const S = 34;
/** Corporation traces: width, focused width, and the distance between neighbouring slots. */
const TRACE_WIDTH = 1.8;
const FOCUS_TRACE_WIDTH = 2.3;
const TRACE_SPACING = 2.6;
/** Extra width of the under-stroke that separates crossing traces. */
const TRACE_HALO = 1.2;
/** A lane's pale core is at least this wide, and wide enough for every corporation's slot. */
const MIN_CORE_WIDTH = 9;
/** The darker casing shows this much either side of the core. */
const CASING_EDGE = 1.1;
/** The interchange disk where three spokes meet is this much wider than the lane, all round. */
const JUNCTION_MARGIN = 0.8;
/**
 * A junction served by up to this many corporations draws their traces through it as branching
 * lines (two of them must cross once); busier junctions draw spokes under an interchange disk.
 */
const JUNCTION_TREE_MAX_CORPS = 2;
/** Radius of the rounded corner where a junction's traces turn from one spoke into another. */
const JUNCTION_BEND_RADIUS = S * 0.15;
/** Radius of the rounded corner where a junction's branch trace joins its trunk. */
const BRANCH_JOIN_RADIUS = S * 0.08;
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
/** A dangling lane stops at a bar this far (in centre-to-edge distances) short of the planet's edge, clear of its name. */
const DANGLE_INSET = 0.24;
/** The bar is this much longer than the lane is wide. */
const DANGLE_OVERHANG = 2;

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

function add(a: Point, b: Point, scale = 1): Point {
  return { x: a.x + b.x * scale, y: a.y + b.y * scale };
}

/** Whether a lane facing the planet at a hex key from one of its sides runs into it. */
type Connects = (planetKey: string, side: DirectionName) => boolean;

const OPEN_HUBS: Connects = () => true;

/** The stub from a planet's edge on `side` to its badge's edge, for previews drawn over the badge. */
function stubPoints(planetHex: Axial, side: DirectionName): { from: Point; to: Point } {
  const planetCenter = hexToPixel(planetHex, S);
  const outward = edgeMidpoint(side, S);
  const length = Math.hypot(outward.x, outward.y);
  return { from: add(planetCenter, outward), to: add(planetCenter, outward, BADGE_RADIUS / length) };
}

/** One stroke of the lane network (a tile's route piece or a planet stub) and who serves it. */
interface LaneStroke {
  piece: LanePiece;
  /** The charted tile the stroke belongs to (for a stub, the tile whose exit runs into the planet). */
  tileKey: string;
  service: string[];
  /** Freshness keys (its exits, or the stub) any of which, when new, make the stroke draw in. */
  drawKeys: string[];
  /** Prefix of the freshness key for a corporation's service on the stroke's tile. */
  serviceKey: string;
  /** The stroke stops short at a dangling bar, so it ends flat there. */
  dangling: boolean;
}

/** One corporation's trace along part of a lane. */
interface TraceStroke {
  key: string;
  corpId: string;
  d: string;
  tileKey: string;
  /** As for the lane stroke under it: when new, the trace draws in. */
  drawKeys: string[];
  serviceKey: string;
}

interface Junction {
  key: string;
  at: Point;
  drawKeys: string[];
}

/** A lane that faces an exit-limited planet without an exit there (facility rules): it stops at a bar. */
interface DanglingEnd {
  key: string;
  planet: PlanetFacilities;
  /** Where the lane stops, and the unit vector across it there. */
  at: Point;
  across: Point;
}

interface LaneNetwork {
  strokes: LaneStroke[];
  traces: TraceStroke[];
  /** Interchange disks, at junctions too busy to draw their traces through. */
  junctions: Junction[];
  dangling: DanglingEnd[];
  /** Every exit, stub and service key, for spotting what is new. */
  keys: string[];
}

function exitKey(tileKey: string, exit: DirectionName): string {
  return `${tileKey}:x:${exit}`;
}

/**
 * The exit a two-exit route is drawn from: one that continues another lane or runs into a planet,
 * so a newly charted lane draws in from the network it extends.
 */
function anchorExit(tile: TileState, exitsByKey: Map<string, DirectionName[]>, hubs: Map<string, Planet>): DirectionName | undefined {
  return tile.exits.find((exit) => {
    const facing = hexKey(neighbor(tile.hex, exit));
    return hubs.has(facing) || (exitsByKey.get(facing) ?? []).includes(oppositeOf(exit));
  });
}

/**
 * Each serving corporation's traces on a tile, at the slots `order` gives them: along the route
 * of a two-exit tile, along the trunk and branch of a junction drawn as a tree, otherwise along
 * each spoke (under an interchange disk).
 */
function tileTraces(
  tile: TileState,
  pieces: LanePiece[],
  order: LaneOrder,
  trims: Partial<Record<DirectionName, number>>,
  serviceKey: string,
): TraceStroke[] {
  const tileKey = hexKey(tile.hex);
  const slot = (exit: DirectionName, corp: string): number => slotOffset(order, tile.hex, exit, corp) * TRACE_SPACING;
  const stroke = (key: string, corpId: string, d: string, exits: DirectionName[]): TraceStroke => ({
    key: `${key}:${corpId}`,
    corpId,
    d,
    tileKey,
    drawKeys: exits.map((exit) => exitKey(tileKey, exit)),
    serviceKey,
  });
  const ends = (piece: LanePiece): DirectionName[] =>
    [piece.startPort?.exit, piece.endPort?.exit].filter((exit): exit is DirectionName => exit !== undefined);
  const junction = order.trunks.get(tileKey);
  if (junction === undefined) {
    return pieces.flatMap((piece) => {
      const [first, last] = [piece.startPort?.exit ?? piece.endPort?.exit, piece.endPort?.exit ?? piece.startPort?.exit];
      if (first === undefined || last === undefined) return [];
      return tile.service.map((corp) => stroke(piece.key, corp, tracePath(piece, slot(first, corp), slot(last, corp)), ends(piece)));
    });
  }
  const [from, to] = junction.trunk;
  const trunk = trunkPiece(tile.hex, from, to, S, JUNCTION_BEND_RADIUS, trims);
  return tile.service.flatMap((corp) => {
    const [start, end] = [slot(from, corp), slot(to, corp)];
    const offset = slot(junction.branch, corp);
    const branch = branchTrace(trunk, start, end, tile.hex, junction.branch, offset, S, BRANCH_JOIN_RADIUS, trims[junction.branch] ?? 0);
    return [
      stroke(trunk.key, corp, tracePath(trunk, start, end), [from, to]),
      stroke(`${tileKey}~${junction.branch}`, corp, branch.path, [junction.branch]),
    ];
  });
}

/**
 * The drawn lane network: each charted tile's route through its exits; a stub into any planet an
 * exit faces and `connects` into (every planet, while they are open hubs; under the facility rules
 * only through a claimed exit); the dangling ends of lanes that face a planet without an exit,
 * where the route stops short at a bar; and the corporations' traces along them, ordered across
 * the whole network by `solveLaneOrder` (slots follow the game's corporation order `corpIds`).
 */
function buildNetwork(
  tiles: TileState[],
  planetsByKey: Map<string, Planet>,
  corpIds: string[],
  connects: Connects = OPEN_HUBS,
  danglingPlanets: PlanetFacilities[] = [],
): LaneNetwork {
  const order = solveLaneOrder(tiles, corpIds, { treeMaxCorps: JUNCTION_TREE_MAX_CORPS, isHub: (key) => planetsByKey.has(key) });
  const exitsByKey = new Map(tiles.map((tile) => [hexKey(tile.hex), tile.exits] as const));
  const cutBack = apothem(S) * DANGLE_INSET;
  const trims = new Map<string, Partial<Record<DirectionName, number>>>();
  for (const planet of danglingPlanets) {
    for (const side of planet.dangling) {
      const tileKey = hexKey(neighbor(planet.hex, side));
      trims.set(tileKey, { ...trims.get(tileKey), [oppositeOf(side)]: cutBack });
    }
  }
  const strokes: LaneStroke[] = [];
  const traces: TraceStroke[] = [];
  const junctions: Junction[] = [];
  const keys: string[] = [];
  const routes = new Map<string, LanePiece[]>();
  for (const tile of tiles) {
    const tileKey = hexKey(tile.hex);
    const tileTrims = trims.get(tileKey) ?? {};
    const startExit = anchorExit(tile, exitsByKey, planetsByKey);
    const route = tileRoute(tile.hex, tile.exits, S, { startExit, trims: tileTrims });
    routes.set(tileKey, route.pieces);
    const serviceKey = `${tileKey}:s:`;
    keys.push(...tile.exits.map((exit) => exitKey(tileKey, exit)), ...tile.service.map((corp) => serviceKey + corp));
    for (const piece of route.pieces) {
      const ends: DirectionName[] = [];
      if (piece.startPort) ends.push(piece.startPort.exit);
      if (piece.endPort) ends.push(piece.endPort.exit);
      strokes.push({
        piece,
        tileKey,
        service: tile.service,
        drawKeys: ends.map((exit) => exitKey(tileKey, exit)),
        serviceKey,
        dangling: ends.some((exit) => tileTrims[exit] !== undefined),
      });
    }
    traces.push(...tileTraces(tile, route.pieces, order, tileTrims, serviceKey));
    if (route.junction && !order.trunks.has(tileKey)) {
      junctions.push({ key: tileKey, at: route.junction, drawKeys: tile.exits.map((exit) => exitKey(tileKey, exit)) });
    }
    for (const exit of tile.exits) {
      const facing = neighbor(tile.hex, exit);
      const side = oppositeOf(exit);
      if (planetsByKey.has(hexKey(facing)) && connects(hexKey(facing), side)) {
        const stub = stubPiece(facing, side, S);
        keys.push(stub.key);
        const drawKeys = [stub.key, exitKey(tileKey, exit)];
        strokes.push({ piece: stub, tileKey, service: tile.service, drawKeys, serviceKey, dangling: false });
        for (const corpId of tile.service) {
          const d = tracePath(stub, slotOffset(order, tile.hex, exit, corpId) * TRACE_SPACING);
          traces.push({ key: `${stub.key}:${corpId}`, corpId, d, tileKey, drawKeys, serviceKey });
        }
      }
    }
  }
  const dangling = danglingPlanets.flatMap((planet) =>
    planet.dangling.map((side): DanglingEnd => {
      const exit = oppositeOf(side);
      const pieces = routes.get(hexKey(neighbor(planet.hex, side))) ?? [];
      const end = pieces.map((piece) => portEnd(piece, exit)).find((found) => found !== null);
      // Should the tiles not show the lane (a replay frame in between), the bar goes where its end would be.
      const outward = edgeMidpoint(side, S);
      const at = end?.at ?? add(hexToPixel(planet.hex, S), outward, 1 + DANGLE_INSET);
      const along = end?.tangent ?? { x: outward.x / apothem(S), y: outward.y / apothem(S) };
      return { key: `${hexKey(planet.hex)}:${side}`, planet, at, across: { x: -along.y, y: along.x } };
    }),
  );
  return { strokes, traces, junctions, dangling, keys };
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
 * The lane the preview action would leave on its hex: the tile's whole resulting exit set, drawn
 * with the same geometry as built lanes. A new exit facing an exit-limited planet claims an open
 * exit there if it has one (`claims`); service claims nothing.
 */
function previewNetwork(
  preview: HexAction,
  tiles: TileState[],
  planetsByKey: Map<string, Planet>,
  corp: string,
  connects: Connects,
  claims: Connects,
): LaneNetwork {
  const existing = tiles.find((t) => hexKey(t.hex) === hexKey(preview.hex))?.exits ?? [];
  let exits: DirectionName[];
  if (preview.type === "chart") exits = preview.exits;
  else if (preview.type === "upgrade") exits = [...existing, preview.exit];
  else exits = existing;
  return buildNetwork([{ hex: preview.hex, exits, service: [corp] }], planetsByKey, [corp], preview.type === "service" ? connects : claims);
}

/** Width of a lane's core: at least MIN_CORE_WIDTH, and room for every slot's trace with a margin. */
function coreWidth(corporationCount: number): number {
  const outermost = ((corporationCount - 1) / 2) * TRACE_SPACING;
  return Math.max(MIN_CORE_WIDTH, 2 * outermost + TRACE_WIDTH + 1.5);
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
  const network = useMemo(
    () => buildNetwork(tiles, planetsByKey, corpIds, connects, facilities?.planets),
    [tiles, planetsByKey, corpIds, connects, facilities],
  );
  // Freshness follows exits, stubs and service as they are added, so an upgrade that reshapes a
  // tile draws in only its new arm.
  const fresh = useFreshKeys(network.keys);
  const maskId = `hexmap-badges-${useId().replace(/:/g, "")}`;
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
  const core = coreWidth(corpIds.length);
  const casing = core + 2 * CASING_EDGE;
  const [boxX, boxY, boxWidth, boxHeight] = box.split(" ").map(Number);
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
        {/* Lanes and traces stop in a clean circle at a planet's badge, even when the planet is dimmed. */}
        <mask id={maskId} maskUnits="userSpaceOnUse" x={boxX} y={boxY} width={boxWidth} height={boxHeight}>
          <rect x={boxX} y={boxY} width={boxWidth} height={boxHeight} fill="#fff" />
          {hubs.map((hub) => {
            const center = hexToPixel(hub.hex, S);
            return <circle key={hexKey(hub.hex)} cx={center.x} cy={center.y} r={BADGE_RADIUS - 0.5} fill="#000" />;
          })}
        </mask>
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

      <LaneLayers
        network={network}
        fresh={fresh}
        focusId={focus?.id ?? null}
        corpIds={corpIds}
        core={core}
        casing={casing}
        mask={`url(#${maskId})`}
        superseded={preview?.type === "upgrade" && focus ? hexKey(preview.hex) : null}
      />

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
        <PreviewLane
          network={previewNetwork(preview, tiles, planetsByKey, focus.id, connects, claims)}
          color={corporationColor(focus.id, corpIds)}
          core={core}
          casing={casing}
          mask={`url(#${maskId})`}
        />
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

      {network.dangling.length > 0 && (
        <g className="hexmap__dangling">
          {network.dangling.map((end) => {
            const half = (casing + DANGLE_OVERHANG) / 2;
            const d = line(add(end.at, end.across, -half), add(end.at, end.across, half));
            return (
              <g key={end.key}>
                <title>{`Dangling lane: ${end.planet.name} has no exit on this side, so the lane does not connect. A facility built there can give it the new exit.`}</title>
                <path d={d} className="hexmap__dangle-halo" />
                <path d={d} className="hexmap__dangle" />
              </g>
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

interface LaneLayersProps {
  network: LaneNetwork;
  fresh: Set<string>;
  focusId: string | null;
  corpIds: string[];
  core: number;
  casing: number;
  mask: string;
  /** The tile whose current shape a previewed upgrade replaces: drawn faintly under the preview. */
  superseded: string | null;
}

/**
 * The lane network as hyperspace routes: every casing, then every core, then the corporations'
 * traces (the focused one last), then the interchange disks, so routes merge without seams at
 * borders and junctions. Glows in a corporation's colour sit under the casings: briefly behind
 * what was just built, steadily behind the focused corporation's network.
 */
function LaneLayers({ network, fresh, focusId, corpIds, core, casing, mask, superseded }: LaneLayersProps) {
  const { strokes, traces, junctions } = network;
  const drawsIn = (keys: string[]): boolean => keys.some((key) => fresh.has(key));
  const fadeClass = (tileKey: string): string => (tileKey === superseded ? " hexmap__route--superseded" : "");
  const strokeClass = (base: string, stroke: LaneStroke): string =>
    `${base}${drawsIn(stroke.drawKeys) ? ` ${base}--fresh` : ""}${stroke.dangling ? " hexmap__route--dangling" : ""}${fadeClass(stroke.tileKey)}`;
  const pathOf = (stroke: LaneStroke): string => piecePath(stroke.piece);
  const glows = strokes.flatMap((stroke) => {
    const building = stroke.service.filter((corpId) => fresh.has(stroke.serviceKey + corpId));
    const builders = building.length > 0 ? building : drawsIn(stroke.drawKeys) ? stroke.service.slice(0, 1) : [];
    const glow = builders.map((corpId) => ({ corpId, focus: false }));
    if (focusId !== null && stroke.service.includes(focusId) && !builders.includes(focusId)) glow.push({ corpId: focusId, focus: true });
    return glow.map(({ corpId, focus }) => (
      <path
        key={`${stroke.piece.key}:${corpId}`}
        d={pathOf(stroke)}
        stroke={corporationColor(corpId, corpIds)}
        strokeWidth={casing + 3}
        className={`hexmap__route-glow${focus ? " hexmap__route-glow--focus" : ""}`}
      />
    ));
  });
  // Each corporation's traces form one group, dimmed as a whole so overlapping ends at hex
  // borders do not show as darker dots; the focused corporation's group is painted last.
  const traceCorps = corpIds
    .filter((corpId) => traces.some((trace) => trace.corpId === corpId))
    .sort((a, b) => Number(a === focusId) - Number(b === focusId));
  return (
    <g className="hexmap__routes" mask={mask}>
      <g>{glows}</g>
      <g>
        {strokes.map((stroke) => (
          <path
            key={stroke.piece.key}
            d={pathOf(stroke)}
            strokeWidth={casing}
            className={strokeClass("hexmap__route-casing", stroke)}
            pathLength={drawsIn(stroke.drawKeys) ? 1 : undefined}
          />
        ))}
      </g>
      <g>
        {strokes.map((stroke) => (
          <path
            key={stroke.piece.key}
            d={pathOf(stroke)}
            strokeWidth={core}
            className={strokeClass("hexmap__route-core", stroke)}
            pathLength={drawsIn(stroke.drawKeys) ? 1 : undefined}
          />
        ))}
      </g>
      <g>
        {traceCorps.map((corpId) => (
          <g key={corpId} className={`hexmap__trace-group${focusId !== null && corpId !== focusId ? " hexmap__trace-group--dimmed" : ""}`}>
            {(["hexmap__trace-halo", "hexmap__trace"] as const).map((layer) =>
              traces
                .filter((trace) => trace.corpId === corpId)
                .map((trace) => {
                  const isFresh = fresh.has(trace.serviceKey + corpId) || drawsIn(trace.drawKeys);
                  const width = corpId === focusId ? FOCUS_TRACE_WIDTH : TRACE_WIDTH;
                  // The core-coloured under-strokes go first, and part the traces of corporations
                  // painted earlier wherever this corporation's trace crosses them.
                  return (
                    <path
                      key={`${layer}:${trace.key}`}
                      d={trace.d}
                      stroke={layer === "hexmap__trace" ? corporationColor(corpId, corpIds) : undefined}
                      strokeWidth={layer === "hexmap__trace" ? width : width + TRACE_HALO}
                      className={`${layer}${isFresh ? " hexmap__trace--fresh" : ""}${fadeClass(trace.tileKey)}`}
                      pathLength={isFresh ? 1 : undefined}
                    />
                  );
                }),
            )}
          </g>
        ))}
      </g>
      {/* At busy junctions the spokes meet under an interchange disk, like a small planet hub, which also hides where their traces join. */}
      <g>
        {junctions.map((junction) => (
          <circle
            key={junction.key}
            cx={junction.at.x}
            cy={junction.at.y}
            r={core / 2 + JUNCTION_MARGIN}
            strokeWidth={CASING_EDGE * 1.15}
            className={`hexmap__junction${drawsIn(junction.drawKeys) ? " hexmap__junction--fresh" : ""}${fadeClass(junction.key)}`}
          />
        ))}
      </g>
    </g>
  );
}

/**
 * The lane a previewed build would leave, in the builder's colour: translucent bands (one group,
 * so overlaps do not darken), an interchange disk if it would have one, and a dashed trace.
 */
function PreviewLane(props: { network: LaneNetwork; color: string; core: number; casing: number; mask: string }) {
  const { network, color, core, casing, mask } = props;
  return (
    <g className="hexmap__preview" mask={mask} stroke={color}>
      <g className="hexmap__preview-bands">
        {network.strokes.map(({ piece }) => (
          <path key={piece.key} d={piecePath(piece)} strokeWidth={casing} />
        ))}
        {network.junctions.map((junction) => (
          <circle key={junction.key} cx={junction.at.x} cy={junction.at.y} r={core / 2 + JUNCTION_MARGIN + CASING_EDGE} fill={color} stroke="none" />
        ))}
      </g>
      {network.traces.map((trace) => (
        <path key={trace.key} d={trace.d} className="hexmap__preview-trace" />
      ))}
      {network.junctions.map((junction) => (
        <circle key={junction.key} cx={junction.at.x} cy={junction.at.y} r={core / 2 + JUNCTION_MARGIN} className="hexmap__preview-junction" />
      ))}
    </g>
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
          <path d={line(stub.from, stub.to)} stroke={color} strokeWidth={MIN_CORE_WIDTH * 0.8} />
          <circle cx={stub.from.x} cy={stub.from.y} r={MIN_CORE_WIDTH * 0.9} stroke={color} className="hexmap__facility-preview-ring" />
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
