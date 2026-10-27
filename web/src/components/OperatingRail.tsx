import type { ReactNode } from "react";
import type { GameState } from "../api";
import { corpColor, findCorporation, operatingQueue, playerName } from "../selectors";
import type { StepStage } from "../selectors";
import { Ticker } from "../playback/Ticker";
import { FleetIcons } from "./DeathStar";
import { Help } from "./Help";

interface OperatingRailProps {
  state: GameState;
  /** The corporation whose network the map emphasizes. */
  focusCorp: string | null;
  onFocus: (corpId: string) => void;
  /** The operating corporation's panel, shown inside its expanded entry. */
  children: ReactNode;
}

const STAGE_MARK: Record<StepStage, string> = { done: "✓", current: "▶", upcoming: "" };
const CURRENT_CHIP: Partial<Record<GameState["phase"], string>> = { network: "operating", fleet: "fleets", dividend: "dividend" };

/**
 * The operating round's corporations, top to bottom in the order they operate. The current one
 * is expanded and holds its action panel. Animation anchors: data-order-corp, data-corp-id (the
 * operating views have no corporation cards), data-treasury-for, data-fleets-for.
 */
export function OperatingRail({ state, focusCorp, onFocus, children }: OperatingRailProps) {
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
              <button
                type="button"
                className="rentry__summary"
                onClick={() => onFocus(corp.id)}
                aria-pressed={focused}
                title={focused ? "Showing this network on the map" : "Show this network on the map"}
              >
                <span className="rentry__mark" aria-hidden>
                  {STAGE_MARK[entry.stage] || index + 1}
                </span>
                <span className="rentry__id">{corp.id}</span>
                <span className="rentry__who">
                  <span className="rentry__president">{playerName(state, corp.president)}</span>
                  <span className={`rentry__chip rentry__chip--${closed ? "closed" : entry.stage}`}>{chip}</span>
                </span>
                <span className="rentry__nums">
                  <span title="Share price">
                    <span className="rentry__k">price</span>{" "}
                    <span className="num">
                      <Ticker value={corp.price} />
                    </span>
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
                  {state.deathStar && !closed && (
                    <FleetIcons
                      corpId={corp.id}
                      fleets={corp.fleets}
                      limit={state.deathStar.fleets.limit}
                      item={state.deathStar.fleets.item}
                    />
                  )}
                </span>
              </button>
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
