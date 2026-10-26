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
