import type { Action, Axial, GameState } from "../api";
import { listText, surrenderChoice } from "../chains";
import type { SurrenderChoice } from "../chains";
import { pairUsage, pairUsageText } from "../deathstar";
import { sameHex } from "../hex";
import { useHotkeys } from "../hotkeys";
import { playerName } from "../selectors";
import { FleetIcons } from "./DeathStar";
import { Help } from "./Help";

interface SurrenderActionsProps {
  state: GameState;
  /** The planet picked on the map, whose option is marked; null for none. */
  selectedPlanet: Axial | null;
  /** Offer the choices; false shows them read-only while someone else chooses. */
  interactive: boolean;
  busy: boolean;
  keyboard: boolean;
  /** Hovering or focusing an option shows its planet on the map. */
  onHighlight: (hex: Axial | null) => void;
  onAct: (action: Action) => void;
}

/** What giving up one facility costs, for its button. */
function lossText(option: SurrenderChoice): string {
  return option.loss > 0 ? `revenue ${option.revenue} (−${option.loss})` : `revenue stays ${option.revenue}`;
}

/**
 * A seizure under the chain rules: the corporation choosing which facility the Empire takes, what
 * it earns now, and for each planet where it holds one, from the server's legal actions, what it
 * would still earn after giving that one up. The cheapest loss comes first.
 */
export function SurrenderActions({ state, selectedPlanet, interactive, busy, keyboard, onHighlight, onAct }: SurrenderActionsProps) {
  const choice = surrenderChoice(state);
  const options = choice?.options ?? [];
  const keys: Record<string, () => void | false> = {};
  if (interactive) {
    options.slice(0, 9).forEach((option, i) => {
      keys[String(i + 1)] = () => (busy ? false : onAct(option.action));
    });
  }
  useHotkeys(keys, interactive && keyboard);

  if (!choice || !state.deathStar) return null;
  const { corp, waiting } = choice;
  const deathStar = state.deathStar;
  const price = deathStar.fleets.price;
  const usage = pairUsage(corp, "facility", true);
  const last = corp.fleets === 1;
  const short = last && corp.treasury < price;
  const president = playerName(state, corp.president);

  return (
    <div className="fleetpanel">
      <div className="fleetpanel__head">
        <span className="netpanel__label">
          Seizure
          <Help topic="seizure" />
        </span>
        <FleetIcons corpId={corp.id} fleets={corp.fleets} limit={deathStar.fleets.limit} item="facility" anchor={false} runs="chain" />
        <span className="fleetpanel__count num">
          {corp.fleets} of {deathStar.fleets.limit}
        </span>
      </div>

      <dl className="fleetpanel__facts">
        <div>
          <dt>Revenue now</dt>
          <dd className="num">
            {corp.revenue.total}
            {usage && <small>{pairUsageText(usage)}</small>}
          </dd>
        </div>
        <div>
          <dt>
            Next facility
            <Help topic="facilitySupply" />
          </dt>
          <dd className="num">{price}</dd>
        </div>
      </dl>

      <p className={`fleetpanel__note${short ? " fleetpanel__note--danger" : ""}`} role={short ? "alert" : undefined}>
        <strong>The Empire demands a facility.</strong> {corp.id} hands over one of its choice: it turns Imperial, keeps its
        slot and exit, and earns for nobody.{" "}
        {last &&
          (short
            ? `It is ${corp.id}'s only facility, and its treasury of ${corp.treasury} cannot build another at ${price}: unless it withholds enough first, it goes bankrupt at its next turn.`
            : `It is ${corp.id}'s only facility: it must build another at its next turn, ${price} at today's price.`)}
        {waiting.length > 0 && ` Then ${listText(waiting)} ${waiting.length === 1 ? "chooses" : "choose"}.`}
      </p>

      {!interactive && <p className="netpanel__hint">{president} is choosing which facility to give up…</p>}
      <div className="facility-options">
        {options.map((option, i) => {
          const selected = selectedPlanet !== null && sameHex(option.action.planet, selectedPlanet);
          return (
            <button
              type="button"
              key={option.name}
              className={`facility-option${selected ? " facility-option--selected" : ""}`}
              disabled={busy || !interactive}
              onMouseEnter={() => onHighlight(option.action.planet)}
              onMouseLeave={() => onHighlight(null)}
              onFocus={() => onHighlight(option.action.planet)}
              onBlur={() => onHighlight(null)}
              onClick={() => onAct(option.action)}
            >
              <span className="facility-option__label">
                Give up the facility at {option.name}
                {interactive && i < 9 && <kbd>{i + 1}</kbd>}
              </span>
              <span className="facility-option__sub">{lossText(option)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
