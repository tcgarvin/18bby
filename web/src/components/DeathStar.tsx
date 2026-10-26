import type { DeathStarState } from "../api";
import { gameEnd, pendingStages, resultLabel, resultText, stageCubes, stageProgress, supplyText } from "../deathstar";
import { Help } from "./Help";

/**
 * The station in SVG units, centred on the origin with radius `r`: a grey sphere, its equatorial
 * trench and the superlaser dish. Drawn inside an `<svg>` (the map) or by `DeathStarGlyph`.
 */
export function DeathStarShape({ r }: { r: number }) {
  return (
    <g className="dstar">
      <circle r={r} className="dstar__body" />
      <path d={`M${-r},0 A${r},${r * 0.28} 0 0 0 ${r},0`} className="dstar__trench" />
      <circle cx={-r * 0.36} cy={-r * 0.38} r={r * 0.27} className="dstar__dish" />
      <circle cx={-r * 0.36} cy={-r * 0.38} r={r * 0.07} className="dstar__focus" />
    </g>
  );
}

/** The station as a small inline icon. */
export function DeathStarGlyph({ size = 16 }: { size?: number }) {
  return (
    <svg className="dstar-glyph" width={size} height={size} viewBox="-10 -10 20 20" aria-hidden>
      <DeathStarShape r={9} />
    </svg>
  );
}

/** One fleet: a wedge-shaped hull, filled when owned and an outline for an empty slot. */
function FleetShip({ owned }: { owned: boolean }) {
  return (
    <svg className={`fleet${owned ? " fleet--owned" : ""}`} width="15" height="10" viewBox="0 0 15 10" aria-hidden>
      <path d="M1,5 L14,1 L14,9 Z" />
    </svg>
  );
}

interface FleetIconsProps {
  corpId: string;
  fleets: number;
  limit: number;
  /** Mark this as the corporation's fleet anchor for replays; leave off for second copies. */
  anchor?: boolean;
}

/** A corporation's fleets as ship icons, with empty slots up to the limit. */
export function FleetIcons({ corpId, fleets, limit, anchor = true }: FleetIconsProps) {
  const slots = Math.max(limit, fleets);
  return (
    <span
      className="fleets"
      data-fleets-for={anchor ? corpId : undefined}
      title={`${fleets} of ${limit} fleets: each runs one revenue pair`}
      aria-label={`${fleets} of ${limit} fleets`}
      role="img"
    >
      {Array.from({ length: slots }, (_, i) => (
        <FleetShip key={i} owned={i < fleets} />
      ))}
    </span>
  );
}

/**
 * The Death Star track and the fleet supply, in a strip under the top bar for the whole game:
 * cubes per stage, the stage being built with its contract value and what happens when it fills,
 * when the game ends, and what the next fleet costs. Animation anchors: data-death-star-track,
 * data-fleet-supply.
 */
export function DeathStarBar({ deathStar, over = false }: { deathStar: DeathStarState; over?: boolean }) {
  const progress = stageProgress(deathStar);
  const pending = pendingStages(deathStar);
  const end = gameEnd(deathStar);
  return (
    <section className="dsbar" aria-label="Death Star track">
      <span className="dsbar__title">
        <DeathStarGlyph />
        Death Star
        <Help topic="deathStar" />
      </span>

      <ol className="dsbar__track" data-death-star-track aria-label={`${deathStar.cubes} of ${deathStar.totalCubes} cubes`}>
        {deathStar.stages.map((stage, i) => {
          const cubes = stageCubes(deathStar, i);
          const state = stage.resolved ? "resolved" : stage.filled ? "pending" : i === progress.index ? "current" : "upcoming";
          return (
            <li
              key={stage.name}
              className={`dsstage dsstage--${state}`}
              title={`${i + 1}. ${stage.name}: contracts score ${stage.value} while it is being built. When it fills: ${resultText(stage.result, deathStar)}.`}
            >
              <span className="dsstage__name">
                {stage.name}
                <span className="dsstage__result">{resultLabel(stage.result)}</span>
              </span>
              <span className="dsstage__cubes" aria-hidden>
                {Array.from({ length: deathStar.cubesPerStage }, (_, c) => (
                  <span key={c} className={`dscube${c < cubes ? " dscube--on" : ""}`} />
                ))}
              </span>
            </li>
          );
        })}
      </ol>

      <span className="dsbar__now">
        {deathStar.launched ? (
          <strong>Launched: the Battle of Yavin</strong>
        ) : over ? (
          <strong>Never finished</strong>
        ) : pending.length > 0 ? (
          <>
            <strong>{pending.map((stage) => stage.name).join(" and ")} built:</strong>{" "}
            {pending.map((stage) => resultText(stage.result, deathStar)).join("; then ")} at the end of this round
          </>
        ) : progress.stage ? (
          <>
            <strong>{progress.stage.name}</strong> · contracts <strong className="num">{deathStar.contractValue}</strong>
            <Help topic="contract" />· {progress.toFill} {progress.toFill === 1 ? "cube" : "cubes"} to{" "}
            {resultLabel(progress.stage.result).toLowerCase()}
            <Help topic={progress.stage.result === "seizure" ? "seizure" : progress.stage.result === "move" ? "siteMove" : "launch"} />
          </>
        ) : null}
      </span>

      <span className="dsbar__end" title={end.reason === "launch" ? "The station launched" : "If the station is not finished first"}>
        {over ? "Ended" : "Ends"} after round <strong className="num">{end.round}</strong>
        {end.reason === "launch" ? " (launch)" : over ? " (backstop)" : " or at launch"}
      </span>

      <span className="dsbar__fleets">
        Fleet
        <strong className="dsbar__price num" data-fleet-supply>
          {deathStar.fleets.price}
        </strong>
        <span className="muted">{supplyText(deathStar)}</span>
        <Help topic="fleetSupply" />
      </span>
    </section>
  );
}
