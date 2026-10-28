import type { ReactNode } from "react";
import type { CorporationState, GameState } from "../api";
import { corpColor, findCorporation, operatingQueue, playerName } from "../selectors";
import type { StepStage } from "../selectors";
import { Ticker } from "../playback/Ticker";
import { FleetIcons } from "./DeathStar";
import { Help } from "./Help";

interface OperatingRailProps {
  state: GameState;
  /** The corporation whose network the map emphasizes, or null for every network. */
  focusCorp: string | null;
  onFocus: (corpId: string) => void;
  /**
   * "operating": the operating round's order, with the current corporation expanded. "corporations":
   * every corporation in its fixed order with its status, for the Map browsed outside an
   * operating round (there is no operating order then).
   */
  mode?: "operating" | "corporations";
  /** The operating corporation's panel, shown inside its expanded entry (operating mode only). */
  children?: ReactNode;
}

const STAGE_MARK: Record<StepStage, string> = { done: "✓", current: "▶", upcoming: "" };
const CURRENT_CHIP: Partial<Record<GameState["phase"], string>> = { network: "operating", fleet: "fleets", dividend: "dividend" };
const STATUS_CHIP: Record<CorporationState["status"], string> = {
  unstarted: "unstarted",
  parred: "parred",
  floated: "floated",
  closed: "bankrupt",
};

/**
 * The corporations down the side of the map. In operating mode they run top to bottom in the
 * order they operate, and the current one is expanded and holds its action panel. Animation
 * anchors: data-order-corp (operating mode), data-corp-id (the map views have no corporation
 * cards), data-treasury-for, data-fleets-for.
 */
export function OperatingRail({ state, focusCorp, onFocus, mode = "operating", children }: OperatingRailProps) {
  if (mode === "corporations") return <CorporationList state={state} focusCorp={focusCorp} onFocus={onFocus} />;
  const queue = operatingQueue(state);
  const firstUpcoming = queue.find((entry) => entry.stage === "upcoming")?.corpId;
  return (
    <aside className="rail" aria-label="Operating order">
      <h2 className="rail__title">
        Operating order
        <Help topic="operatingOrder" />
        <span className="rail__round">{state.roundLabel}</span>
      </h2>
      <ol className="rail__list">
        {queue.map((entry, index) => {
          const corp = findCorporation(state, entry.corpId);
          if (!corp) return null;
          const current = entry.stage === "current";
          const focused = focusCorp === corp.id;
          const closed = corp.status === "closed";
          const chip = closed
            ? "bankrupt"
            : entry.stage === "done"
              ? "done"
              : current
                ? state.phase === "fleet" && state.facilities
                  ? "facilities"
                  : (CURRENT_CHIP[state.phase] ?? "operating")
                : entry.corpId === firstUpcoming
                  ? "up next"
                  : "waiting";
          return (
            <li
              key={corp.id}
              data-order-corp={corp.id}
              data-corp-id={corp.id}
              className={`rentry rentry--${entry.stage}${focused ? " rentry--focused" : ""}${closed ? " rentry--closed" : ""}`}
              style={{ ["--corp" as string]: corpColor(state, corp.id) }}
            >
              <EntrySummary
                state={state}
                corp={corp}
                focused={focused}
                onFocus={onFocus}
                mark={STAGE_MARK[entry.stage] || String(index + 1)}
                chip={chip}
                chipTone={closed ? "closed" : entry.stage}
              />
              {entry.stage !== "upcoming" && entry.log.length > 0 && (
                <ul className="rentry__log">
                  {entry.log.map((line) => (
                    <li key={line.seq}>{line.text}</li>
                  ))}
                </ul>
              )}
              {current && <div className="rentry__panel">{children}</div>}
            </li>
          );
        })}
      </ol>
    </aside>
  );
}

/** Every corporation in its fixed order, with its status; a click shows (or hides) its network. */
function CorporationList({ state, focusCorp, onFocus }: Pick<OperatingRailProps, "state" | "focusCorp" | "onFocus">) {
  const anyFloated = state.corporations.some((corp) => corp.status === "floated" || corp.status === "closed");
  return (
    <aside className="rail rail--corporations" aria-label="Corporations">
      <h2 className="rail__title">
        Corporations
        <Help topic="float" />
        <span className="rail__round">{state.roundLabel}</span>
      </h2>
      <ol className="rail__list">
        {!anyFloated && <li className="rail__empty muted">No corporations floated yet.</li>}
        {state.corporations.map((corp) => {
          const focused = focusCorp === corp.id;
          const closed = corp.status === "closed";
          return (
            <li
              key={corp.id}
              data-corp-id={corp.id}
              className={`rentry rentry--${corp.status}${focused ? " rentry--focused" : ""}${closed ? " rentry--closed" : ""}`}
              style={{ ["--corp" as string]: corpColor(state, corp.id) }}
            >
              <EntrySummary
                state={state}
                corp={corp}
                focused={focused}
                onFocus={onFocus}
                mark={null}
                chip={STATUS_CHIP[corp.status]}
                chipTone={corp.status}
                roomy
              />
            </li>
          );
        })}
      </ol>
    </aside>
  );
}

interface EntrySummaryProps {
  state: GameState;
  corp: CorporationState;
  focused: boolean;
  onFocus: (corpId: string) => void;
  /** The operating-order mark (position, tick or arrow), or null for none. */
  mark: string | null;
  chip: string;
  /** Picks the chip's colours: rentry__chip--<tone>. */
  chipTone: string;
  /** Labelled stats in a grid, with the fleets or facilities on a row of their own (the browsed rail). */
  roomy?: boolean;
}

function EntrySummary({ state, corp, focused, onFocus, mark, chip, chipTone, roomy = false }: EntrySummaryProps) {
  const closed = corp.status === "closed";
  const started = corp.status !== "unstarted";
  const fleetIcons = state.deathStar && (
    <FleetIcons corpId={corp.id} fleets={corp.fleets} limit={state.deathStar.fleets.limit} item={state.deathStar.fleets.item} />
  );
  return (
    <button
      type="button"
      className="rentry__summary"
      onClick={() => onFocus(corp.id)}
      aria-pressed={focused}
      title={
        focused
          ? roomy
            ? "Show all networks on the map"
            : "Showing this network on the map"
          : "Show this network on the map"
      }
    >
      {mark !== null && (
        <span className="rentry__mark" aria-hidden>
          {mark}
        </span>
      )}
      <span className="rentry__id">{corp.id}</span>
      <span className="rentry__who">
        <span className="rentry__president">{corp.president ? playerName(state, corp.president) : corp.homeworld}</span>
        <span className={`rentry__chip rentry__chip--${chipTone}`}>{chip}</span>
      </span>
      <span className="rentry__nums">
        <span title="Share price">
          <span className="rentry__k">price</span>{" "}
          <span className="num">{started && !closed ? <Ticker value={corp.price} /> : "—"}</span>
        </span>
        <span title="Treasury" data-treasury-for={corp.id}>
          <span className="rentry__k">treasury</span>{" "}
          <span className="num">
            <Ticker value={corp.treasury} />
          </span>
        </span>
        <span title="Revenue its network earns now">
          <span className="rentry__k">revenue</span> <span className="num">{corp.revenue.total}</span>
        </span>
        {state.deathStar &&
          !closed &&
          (roomy ? (
            <span className="rentry__supply">
              <span className="rentry__k">{state.deathStar.fleets.item === "facility" ? "Facilities" : "Fleets"}</span>
              {fleetIcons}
            </span>
          ) : (
            fleetIcons
          ))}
      </span>
    </button>
  );
}
