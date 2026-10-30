import type { Action, BuyBlock, CorporationState, GameState, SellAction } from "../api";
import type { GlossaryId } from "../help/glossary";
import { buyBlockText, corpColor, playerName, tradeOptionsFor } from "../selectors";
import type { CorpTradeOptions } from "../selectors";
import { Ticker } from "../playback/Ticker";
import { CertStack } from "./CertStack";
import { supplyItem } from "../facilities";
import { FleetIcons } from "./DeathStar";
import { Help } from "./Help";

interface CorporationBoardProps {
  state: GameState;
  /** Show the buy, sell and par buttons (the human's turn in a stock round). */
  interactive: boolean;
  busy: boolean;
  onAct: (action: Action) => void;
}

/** The glossary entry that explains a buy block, for those that name a rule. */
const BLOCK_HELP: Partial<Record<BuyBlock["reason"], GlossaryId>> = {
  certificate_limit: "certificate",
  holding_limit: "holdingLimit",
};

/**
 * One card per corporation: identity, price and par, treasury, president, and the certificates
 * left in the IPO and the pool, with the legal trades for it inline, or why it cannot be bought.
 * Animation anchors:
 * data-corp-id, data-ipo-for (the IPO stack), data-pool-for (the pool stack, present only when
 * the pool holds shares), data-treasury-for, data-fleets-for (under the Death Star rules).
 */
export function CorporationBoard({ state, interactive, busy, onAct }: CorporationBoardProps) {
  return (
    <div className="cboard">
      {state.corporations.map((corp, index) => (
        <CorporationCard
          key={corp.id}
          state={state}
          corp={corp}
          explain={index === 0}
          options={interactive ? tradeOptionsFor(state, corp.id) : null}
          busy={busy}
          onAct={onAct}
        />
      ))}
    </div>
  );
}

interface CorporationCardProps {
  state: GameState;
  corp: CorporationState;
  /** Show the glossary "?" on the stat labels (only the first card, so the board stays calm). */
  explain: boolean;
  /** Legal trades, or null when the controls are hidden. */
  options: CorpTradeOptions | null;
  busy: boolean;
  onAct: (action: Action) => void;
}

function CorporationCard({ state, corp, explain, options, busy, onAct }: CorporationCardProps) {
  const color = corpColor(state, corp.id);
  const started = corp.status !== "unstarted";
  const closed = corp.status === "closed";
  const fleetLimit = state.deathStar?.fleets.limit;
  const item = supplyItem(state.deathStar);
  const tradable = options !== null && (options.ipoBuys.length > 0 || options.poolBuy !== null || options.sells.length > 0);
  return (
    <article
      data-corp-id={corp.id}
      className={`ccard ccard--${corp.status}${tradable ? " ccard--tradable" : ""}`}
      style={{ ["--corp" as string]: color }}
    >
      <div className="ccard__top">
        <header className="ccard__head">
          <span className="ccard__id">{corp.id}</span>
          <span className="ccard__name" title={corp.name}>
            {corp.name}
          </span>
          <span className="ccard__sub">
            {corp.homeworld}
            <span className={`status status--${corp.status}`}>{closed ? "closed · shares worthless" : corp.status}</span>
            {closed ? <Help topic="bankruptcy" /> : explain && <Help topic="float" />}
          </span>
        </header>

        <dl className={`ccard__stats${fleetLimit !== undefined ? " ccard__stats--fleets" : ""}`}>
          <div className="ccard__price">
            <dt>
              Price
              {explain && <Help topic="sharePrice" />}
            </dt>
            <dd className="num">
              {started && !closed ? <Ticker value={corp.price} /> : "—"}
              {started && !closed && <span className="ccard__par">par {corp.par}</span>}
            </dd>
          </div>
          <div data-treasury-for={corp.id}>
            <dt>
              Treasury
              {explain && <Help topic="treasury" />}
            </dt>
            <dd className="num">
              <Ticker value={corp.treasury} />
            </dd>
          </div>
          <div className="ccard__president">
            <dt>
              President
              {explain && <Help topic="president" />}
            </dt>
            <dd>{corp.president ? playerName(state, corp.president) : "—"}</dd>
          </div>
          {fleetLimit !== undefined && (
            <div className="ccard__fleets">
              <dt>
                {item === "facility" ? "Facilities" : "Fleets"}
                {explain && <Help topic={item === "facility" ? "facility" : "fleet"} />}
              </dt>
              <dd>
                <FleetIcons
                  corpId={corp.id}
                  fleets={corp.fleets}
                  limit={fleetLimit}
                  item={item}
                  runs={state.config.chainRules ? "chain" : "pair"}
                />
              </dd>
            </div>
          )}
        </dl>
      </div>

      <div className="ccard__foot">
        <div className="ccard__certs">
          <div className="certpile" data-ipo-for={corp.id}>
            <CertStack
              corpId={corp.id}
              color={color}
              shares={corp.ipoShares}
              president={!started}
              size="md"
              title={`${corp.ipoShares} ${corp.id} shares in the IPO`}
            />
            <span className="certpile__label">
              IPO
              {explain && <Help topic="ipo" />}
              {started && corp.ipoShares > 0 && <span className="num certpile__price">@{corp.ipoPrice}</span>}
            </span>
          </div>
          {corp.poolShares > 0 && (
            <div className="certpile" data-pool-for={corp.id}>
              <CertStack
                corpId={corp.id}
                color={color}
                shares={corp.poolShares}
                size="md"
                title={`${corp.poolShares} ${corp.id} shares in the pool`}
              />
              <span className="certpile__label">
                Pool
                {explain && <Help topic="pool" />}
                <span className="num certpile__price">@{corp.price}</span>
              </span>
            </div>
          )}
        </div>
        {options && (
          <TradeControls
            state={state}
            corp={corp}
            options={options}
            explain={explain}
            busy={busy}
            onAct={onAct}
          />
        )}
      </div>
    </article>
  );
}

function TradeControls({
  state,
  corp,
  options,
  explain,
  busy,
  onAct,
}: {
  state: GameState;
  corp: CorporationState;
  options: CorpTradeOptions;
  explain: boolean;
  busy: boolean;
  onAct: (action: Action) => void;
}) {
  const parBuys = options.ipoBuys.filter((a) => a.par);
  const ipoBuy = options.ipoBuys.find((a) => !a.par);
  const block = state.buyBlocks[corp.id];
  if (parBuys.length === 0 && !ipoBuy && !options.poolBuy && options.sells.length === 0 && !block) {
    return <div className="trade trade--none">No trade</div>;
  }
  const blockHelp = block && BLOCK_HELP[block.reason];
  return (
    <div className="trade">
      {block && (
        <span className="trade__why">
          {buyBlockText(state, corp, block)}
          {blockHelp && <Help topic={blockHelp} />}
        </span>
      )}
      {parBuys.length > 0 && (
        <div className="trade__group">
          <span className="trade__label">
            Start at par
            {explain && <Help topic="par" />}
          </span>
          {parBuys.map((action) => (
            <button type="button" key={action.par} className="btn btn--trade" disabled={busy} onClick={() => onAct(action)}>
              {action.par}
            </button>
          ))}
        </div>
      )}
      {ipoBuy && (
        <button type="button" className="btn btn--trade btn--buy" disabled={busy} onClick={() => onAct(ipoBuy)}>
          Buy IPO <span className="num">{corp.ipoPrice}</span>
        </button>
      )}
      {options.poolBuy && (
        <button
          type="button"
          className="btn btn--trade btn--buy"
          disabled={busy}
          onClick={() => options.poolBuy && onAct(options.poolBuy)}
        >
          Buy pool <span className="num">{corp.price}</span>
        </button>
      )}
      {options.sells.length > 0 && <SellButtons corp={corp} sells={options.sells} busy={busy} onAct={onAct} />}
    </div>
  );
}

function SellButtons({
  corp,
  sells,
  busy,
  onAct,
}: {
  corp: CorporationState;
  sells: SellAction[];
  busy: boolean;
  onAct: (action: Action) => void;
}) {
  return (
    <div className="trade__group trade__group--sell" role="group" aria-label={`Sell ${corp.id} shares`}>
      <span className="trade__label">Sell</span>
      {sells.map((action) => (
        <button
          type="button"
          key={action.count}
          className="btn btn--trade btn--sell"
          disabled={busy}
          onClick={() => onAct(action)}
          title={`Sell ${action.count} ${corp.id} for ${action.count * corp.price}`}
        >
          {action.count}
        </button>
      ))}
    </div>
  );
}
