import type { GameState } from "../api";
import { siteHexes } from "../deathstar";
import { corpColor, findCorporation } from "../selectors";
import { DeathStarGlyph } from "./DeathStar";
import { Help } from "./Help";

/** Regions, terrain and corporation colors under a map, plus a line on the focused network. */
export function MapLegend({ state, focusCorp }: { state: GameState; focusCorp: string | null }) {
  const focus = findCorporation(state, focusCorp);
  return (
    <div className="legend">
      <span className="legend__item">
        <span className="legend__swatch legend__swatch--core" /> Core
      </span>
      <span className="legend__item">
        <span className="legend__swatch legend__swatch--mid" /> Mid Rim
      </span>
      <span className="legend__item">
        <span className="legend__swatch legend__swatch--outer" /> Outer Rim
      </span>
      <Help topic="region" />
      {state.terrain.length > 0 && (
        <>
          <span className="legend__sep" />
          <span className="legend__item">
            <span className="legend__swatch legend__swatch--asteroid" /> Asteroids
          </span>
          <span className="legend__item">
            <span className="legend__swatch legend__swatch--nebula" /> Nebula
          </span>
          <Help topic="terrain" />
        </>
      )}
      {state.deathStar && (
        <>
          <span className="legend__sep" />
          {siteHexes(state.deathStar, "active").length > 0 && (
            <span className="legend__site">
              <DeathStarGlyph size={14} /> Death Star ({state.deathStar.siteTag})
            </span>
          )}
          {siteHexes(state.deathStar, "reserved").length > 0 && (
            <span className="legend__site">
              <span className="legend__future" /> future site
            </span>
          )}
          <Help topic="contract" />
        </>
      )}
      {state.facilities && (
        <>
          <span className="legend__sep" />
          <span className="legend__item">
            <svg width="11" height="11" viewBox="-5.5 -5.5 11 11" aria-hidden>
              <rect x={-4.25} y={-4.25} width={8.5} height={8.5} rx={1.6} className="legend__facility" />
            </svg>
            facility
          </span>
          <span className="legend__item">
            <svg width="13" height="13" viewBox="-6.5 -6.5 13 13" aria-hidden>
              <path d="M0,-5.3L5.3,0L0,5.3L-5.3,0Z" className="legend__facility legend__facility--imperial" />
              <circle r={1.5} className="legend__facility-dot" />
            </svg>
            Imperial
          </span>
          <Help topic="facility" />
          <span className="legend__item">
            <svg width="8" height="8" viewBox="-4 -4 8 8" aria-hidden>
              <circle r={2.7} className="legend__open-exit" />
            </svg>
            open exit
          </span>
          <span className="legend__item">
            <svg width="14" height="12" viewBox="0 0 14 12" aria-hidden>
              <path d="M0,6H9" className="legend__lane" />
              <path d="M10.5,1.5V10.5" className="legend__dangle" />
            </svg>
            dangling lane
          </span>
          <Help topic="planetExits" />
        </>
      )}
      <span className="legend__sep" />
      {state.corporations.map((c) => (
        <span key={c.id} className="legend__item">
          <span className="legend__line" style={{ background: corpColor(state, c.id) }} /> {c.id}
        </span>
      ))}
      {focus && focus.status === "floated" && (
        <span className="legend__focus">
          {focus.id}: {focus.reachablePlanets.length} planets reachable · revenue {focus.revenue.total}
        </span>
      )}
    </div>
  );
}
