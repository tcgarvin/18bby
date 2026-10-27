import type { Action, Axial, BuildFacilityAction, CorporationState, GameState, PlanetFacilities } from "../api";
import { nextSeizure, pairUsage, pairUsageText, supplyText } from "../deathstar";
import { bestGain, buildGain, facilityChoice, laneOwners, planetsByKey, seizureTarget } from "../facilities";
import type { BuildChoice } from "../facilities";
import { hexKey } from "../hex";
import { useHotkeys } from "../hotkeys";
import { playerName } from "../selectors";
import { FleetIcons } from "./DeathStar";
import { Help } from "./Help";

interface FacilityActionsProps {
  state: GameState;
  corp: CorporationState;
  /** The planet whose builds are shown, picked on the map or from the list. */
  selectedPlanet: Axial | null;
  /** Offer the builds and Finish; false shows a read-only summary. */
  interactive: boolean;
  busy: boolean;
  keyboard: boolean;
  onSelectPlanet: (hex: Axial | null) => void;
  onPreview: (action: BuildFacilityAction | null) => void;
  onAct: (action: Action) => void;
}

interface PlanetBuilds {
  planet: PlanetFacilities;
  choices: BuildChoice[];
  gain: number;
}

/** What one build does, for its button: the revenue it adds, and where its new exit goes. */
function buildEffect(choice: BuildChoice, corp: CorporationState, planet: PlanetFacilities): string {
  const gain = buildGain(choice, corp);
  const revenue = choice.preview === null ? "" : gain > 0 ? `+${gain} revenue this turn` : "adds no revenue this turn";
  const preview = choice.preview;
  let where: string;
  if (!choice.action.exit) where = `open for the next lane charted toward ${planet.name}`;
  else if (!preview) where = "connects the lane there";
  else {
    const reaches = preview.reaches.length > 0 ? `, reaching ${preview.reaches.join(", ")}` : "";
    where = `connects ${laneOwners(preview.lane, corp.id)}${reaches}`;
  }
  return [revenue, where].filter(Boolean).join(" · ");
}

/**
 * The operating corporation's facility step (facility rules): what it owns, what the next facility
 * costs, the seizure it should plan for, and from the server's legal actions the planets it may
 * build on and, for the picked planet, where the new exit can go. Then Finish.
 */
export function FacilityActions(props: FacilityActionsProps) {
  const { state, corp, selectedPlanet, interactive, busy, keyboard, onSelectPlanet, onPreview, onAct } = props;
  const deathStar = state.deathStar;
  const choice = facilityChoice(state, corp);
  const planets = planetsByKey(state.facilities);
  const list: PlanetBuilds[] = [...choice.builds.entries()]
    .flatMap(([key, choices]) => {
      const planet = planets.get(key);
      return planet ? [{ planet, choices, gain: bestGain(choices, corp) }] : [];
    })
    .sort((a, b) => b.gain - a.gain || a.planet.name.localeCompare(b.planet.name));
  const selected = selectedPlanet ? list.find((entry) => hexKey(entry.planet.hex) === hexKey(selectedPlanet)) : undefined;
  const options = interactive && selected ? selected.choices : [];
  const finish = interactive ? choice.finish : null;

  const keys: Record<string, () => void | false> = {
    p: () => (finish && !busy ? onAct(finish) : false),
  };
  if (options.length > 0) {
    options.slice(0, 9).forEach((option, i) => {
      keys[String(i + 1)] = () => (busy ? false : onAct(option.action));
    });
  } else if (interactive) {
    list.slice(0, 9).forEach((entry, i) => {
      keys[String(i + 1)] = () => onSelectPlanet(entry.planet.hex);
    });
  }
  useHotkeys(keys, interactive && keyboard);

  if (!deathStar || !state.facilities) return null;
  const limit = deathStar.fleets.limit;
  const price = deathStar.fleets.price;
  const usage = pairUsage(corp, "facility");
  const seizure = nextSeizure(deathStar);
  const target = seizureTarget(state, corp.id);
  const president = playerName(state, corp.president);

  return (
    <div className="fleetpanel">
      <div className="fleetpanel__head">
        <span className="netpanel__label">
          Facilities
          <Help topic="facility" />
        </span>
        <FleetIcons corpId={corp.id} fleets={corp.fleets} limit={limit} item="facility" anchor={false} />
        <span className="fleetpanel__count num">
          {corp.fleets} of {limit}
        </span>
      </div>

      <dl className="fleetpanel__facts">
        <div>
          <dt>
            Next facility
            <Help topic="facilitySupply" />
          </dt>
          <dd className="num">
            {price}
            <small>{supplyText(deathStar)}</small>
          </dd>
        </div>
        <div>
          <dt>Revenue now</dt>
          <dd className="num">
            {corp.revenue.total}
            {usage && <small>{pairUsageText(usage)}</small>}
          </dd>
        </div>
      </dl>

      {choice.mandatory && (
        <p className="fleetpanel__note">
          {corp.id} owns no facility, so it must build one before it can earn. <Help topic="bankruptcy" />
        </p>
      )}
      {seizure && target && (
        <p
          className={`fleetpanel__note${corp.fleets === 1 && corp.treasury < price ? " fleetpanel__note--danger" : ""}`}
          role={corp.fleets === 1 && corp.treasury < price ? "alert" : undefined}
        >
          <strong>Seizure ahead.</strong>{" "}
          {seizure.cubesToGo === 0
            ? `The ${seizure.stage.name} stage has filled: at the end of this round`
            : `When the ${seizure.stage.name} stage fills (${seizure.cubesToGo} ${seizure.cubesToGo === 1 ? "cube" : "cubes"} to go),`}{" "}
          the Empire takes over each corporation's facility nearest the site: {corp.id}'s at {target.name}.{" "}
          {corp.fleets === 1 &&
            (corp.treasury >= price
              ? `With one facility, ${corp.id} would have none and must build another at its next turn, ${price} at today's price; its treasury of ${corp.treasury} covers that today.`
              : `With one facility, ${corp.id} would have none, and its treasury of ${corp.treasury} cannot build another at ${price}: unless it withholds enough first, it goes bankrupt and its shares become worthless.`)}
          <Help topic="seizure" />
        </p>
      )}

      {!interactive ? (
        <p className="netpanel__hint">{president} is deciding where to build…</p>
      ) : selected && options.length > 0 ? (
        <div className="hex-options">
          <div className="hex-options__head">
            <span>
              {selected.planet.name} · {selected.planet.freeSlots} of {state.facilities.perPlanet}{" "}
              {state.facilities.perPlanet === 1 ? "slot" : "slots"} free · build for <span className="num">{price}</span>
            </span>
            <button type="button" className="link" onClick={() => onSelectPlanet(null)}>
              close <kbd>Esc</kbd>
            </button>
          </div>
          <p className="facility-options__exits">
            {selected.planet.exits} {selected.planet.exits === 1 ? "exit" : "exits"} now
            {selected.planet.claimed.length > 0 && <> · claimed {selected.planet.claimed.join(", ")}</>}
            {selected.planet.unclaimed > 0 && <> · {selected.planet.unclaimed} open</>}
            <Help topic="planetExits" />
          </p>
          <div className="facility-options">
            {options.map((option, i) => (
              <button
                type="button"
                key={JSON.stringify(option.action)}
                className="facility-option"
                disabled={busy}
                onMouseEnter={() => onPreview(option.action)}
                onMouseLeave={() => onPreview(null)}
                onFocus={() => onPreview(option.action)}
                onBlur={() => onPreview(null)}
                onClick={() => onAct(option.action)}
              >
                <span className="facility-option__label">
                  {option.action.exit ? `Give the new exit to the ${option.action.exit} lane` : "Leave the new exit open"}
                  {i < 9 && <kbd>{i + 1}</kbd>}
                </span>
                <span className="facility-option__sub">{buildEffect(option, corp, selected.planet)}</span>
              </button>
            ))}
          </div>
          {selected.planet.dangling.length > 0 && (
            <p className="facility-options__exits muted">
              A dangling lane connects only if you give it the new exit.
              <Help topic="dangling" />
            </p>
          )}
        </div>
      ) : list.length > 0 ? (
        <div className="facility-planets">
          <p className="netpanel__hint">
            Pick a highlighted planet on the map, or one here. Each facility adds an exit to its planet.
          </p>
          <ul className="facility-planets__list">
            {list.map((entry, i) => (
              <li key={hexKey(entry.planet.hex)}>
                <button
                  type="button"
                  className="facility-planet"
                  disabled={busy}
                  onClick={() => onSelectPlanet(entry.planet.hex)}
                  title={`${entry.planet.name}: ${entry.choices.length} ${entry.choices.length === 1 ? "way" : "ways"} to place its new exit`}
                >
                  <span className="facility-planet__name">{entry.planet.name}</span>
                  <span className="facility-planet__gain num">{entry.gain > 0 ? `+${entry.gain}` : "+0"}</span>
                  {i < 9 && <kbd>{i + 1}</kbd>}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="netpanel__hint">
          {choice.atLimit
            ? `${corp.id} has the most facilities a corporation may own.`
            : corp.treasury < price
              ? `${corp.id}'s treasury of ${corp.treasury} cannot build another facility at ${price}.`
              : `${corp.id} has no planet it may build on: none it reaches or points a lane at has a free slot.`}
        </p>
      )}

      {interactive && finish && (
        <button type="button" className="btn btn--block" disabled={busy} onClick={() => onAct(finish)}>
          <span>
            Finish with {corp.fleets} {corp.fleets === 1 ? "facility" : "facilities"} <kbd>P</kbd>
          </span>
        </button>
      )}
    </div>
  );
}
