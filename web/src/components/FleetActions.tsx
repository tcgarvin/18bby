import type { Action, CorporationState, GameState } from "../api";
import { fleetChoice, pairUsage, pairUsageText, seizureRisk, supplyText } from "../deathstar";
import { useHotkeys } from "../hotkeys";
import { playerName } from "../selectors";
import { FleetIcons } from "./DeathStar";
import { Help } from "./Help";

interface FleetActionsProps {
  state: GameState;
  corp: CorporationState;
  /** Offer Buy and Finish; false shows a read-only summary. */
  interactive: boolean;
  busy: boolean;
  keyboard: boolean;
  onAct: (action: Action) => void;
}

/**
 * The operating corporation's fleet step: what it owns, what the next fleet costs and adds to this
 * turn's revenue, the seizure it should plan for, and Buy or Finish from the server's legal actions.
 */
export function FleetActions({ state, corp, interactive, busy, keyboard, onAct }: FleetActionsProps) {
  const deathStar = state.deathStar;
  const choice = fleetChoice(state, corp);
  const buy = interactive ? choice.buy : null;
  const finish = interactive ? choice.finish : null;
  useHotkeys(
    {
      b: () => (buy && !busy ? onAct(buy) : false),
      p: () => (finish && !busy ? onAct(finish) : false),
    },
    interactive && keyboard,
  );
  if (!deathStar) return null;
  const limit = deathStar.fleets.limit;
  const usage = pairUsage(corp);
  const risk = seizureRisk(deathStar, corp.fleets, corp.treasury);
  const president = playerName(state, corp.president);

  return (
    <div className="fleetpanel">
      <div className="fleetpanel__head">
        <span className="netpanel__label">
          Fleets
          <Help topic="fleet" />
        </span>
        <FleetIcons corpId={corp.id} fleets={corp.fleets} limit={limit} anchor={false} />
        <span className="fleetpanel__count num">
          {corp.fleets} of {limit}
        </span>
      </div>

      <dl className="fleetpanel__facts">
        <div>
          <dt>
            Next fleet
            <Help topic="fleetSupply" />
          </dt>
          <dd className="num">
            {deathStar.fleets.price}
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
          {corp.id} owns no fleet, so it must buy one before it can earn. <Help topic="bankruptcy" />
        </p>
      )}
      {risk && (
        <p className={`fleetpanel__note${risk.covered ? "" : " fleetpanel__note--danger"}`} role={risk.covered ? undefined : "alert"}>
          <strong>Seizure ahead.</strong>{" "}
          {risk.cubesToGo === 0
            ? `The ${risk.stage.name} stage has filled: at the end of this round the Empire takes a fleet from everyone.`
            : `When the ${risk.stage.name} stage fills (${risk.cubesToGo} ${risk.cubesToGo === 1 ? "cube" : "cubes"} to go), the Empire takes a fleet from everyone.`}{" "}
          With one fleet, {corp.id} would have none and must buy another at its next turn, {risk.price} at today's price.{" "}
          {risk.covered
            ? `Its treasury of ${corp.treasury} covers that today; keep it in reserve or buy a second fleet.`
            : `Its treasury of ${corp.treasury} cannot cover that: unless it withholds enough first, ${corp.id} goes bankrupt and its shares become worthless.`}
          <Help topic="seizure" />
        </p>
      )}

      {!interactive ? (
        <p className="netpanel__hint">{president} is deciding how many fleets to run…</p>
      ) : (
        <div className="fleetpanel__buttons">
          {buy ? (
            <button type="button" className="btn btn--primary btn--fleet" disabled={busy} onClick={() => onAct(buy)}>
              <span>
                Buy a fleet for <span className="num">{buy.cost}</span> <kbd>B</kbd>
              </span>
              <span className="btn__sub">
                {choice.adds > 0
                  ? `adds +${choice.adds} revenue this turn`
                  : "adds nothing this turn: every pair already runs"}
                {` · treasury ${corp.treasury} → ${corp.treasury - buy.cost}`}
              </span>
            </button>
          ) : (
            <p className="netpanel__hint">
              {choice.atLimit
                ? `${corp.id} has the most fleets a corporation may own.`
                : `${corp.id}'s treasury of ${corp.treasury} cannot buy another fleet at ${deathStar.fleets.price}.`}
            </p>
          )}
          {finish && (
            <button type="button" className="btn btn--block" disabled={busy} onClick={() => onAct(finish)}>
              <span>
                Finish with {corp.fleets} {corp.fleets === 1 ? "fleet" : "fleets"} <kbd>P</kbd>
              </span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
