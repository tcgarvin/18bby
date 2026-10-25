import type { Action, CorporationState, GameState, SellAction } from "../api";
import { corpColor, ownership, playerName, tradeOptionsFor } from "../selectors";
import type { CorpTradeOptions } from "../selectors";
import { Ticker } from "../playback/Ticker";
import { Help } from "./Help";

interface CorporationBoardProps {
  state: GameState;
  /** Show the buy, sell and par buttons (the human's turn in a stock round). */
  interactive: boolean;
  busy: boolean;
  onAct: (action: Action) => void;
}

/**
 * One card per corporation: identity, price and par, IPO, pool, treasury, president and how
 * its shares are split, with the legal trades for it inline. Animation anchors: data-corp-id,
 * data-ipo-for, data-pool-for, data-treasury-for.
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
            <span className={`status status--${corp.status}`}>{corp.status}</span>
            {explain && <Help topic="float" />}
          </span>
        </header>

        <dl className="ccard__stats">
          <div className="ccard__price">
            <dt>
              Price
              {explain && <Help topic="sharePrice" />}
            </dt>
            <dd className="num">
              {started ? <Ticker value={corp.price} /> : "—"}
              {started && <span className="ccard__par">par {corp.par}</span>}
            </dd>
          </div>
          <div data-ipo-for={corp.id}>
            <dt>
              IPO
              {explain && <Help topic="ipo" />}
            </dt>
            <dd className="num">
              {corp.ipoShares}
              {started && corp.ipoShares > 0 && <span className="ccard__at">@{corp.ipoPrice}</span>}
            </dd>
          </div>
          <div data-pool-for={corp.id}>
            <dt>
              Pool
              {explain && <Help topic="pool" />}
            </dt>
            <dd className="num">{corp.poolShares}</dd>
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
        </dl>
      </div>

      <div className="ccard__foot">
        <OwnershipBar state={state} corp={corp} />
        {options && <TradeControls corp={corp} options={options} explain={explain} busy={busy} onAct={onAct} />}
      </div>
    </article>
  );
}

/** The corporation's shares as one bar: each holder's run (president first), then the pool and the IPO. */
function OwnershipBar({ state, corp }: { state: GameState; corp: CorporationState }) {
  const total = state.config.sharesPerCorporation;
  const slices = ownership(state, corp);
  return (
    <div className="obar" aria-label={`${corp.id} ownership`}>
      {slices.map((slice) => {
        const kind = slice.owner === "ipo" ? "ipo" : slice.owner === "pool" ? "pool" : "player";
        const name =
          kind === "ipo" ? (corp.status === "unstarted" ? "Unstarted" : "IPO") : kind === "pool" ? "Pool" : playerName(state, slice.owner);
        const president = slice.owner === corp.president;
        return (
          <span
            key={slice.owner}
            className={`obar__seg obar__seg--${kind}${president ? " obar__seg--president" : ""}`}
            style={{ flexGrow: slice.count, flexBasis: 0, ["--n" as string]: slice.count }}
            data-share-owner={slice.owner}
            title={`${name}: ${slice.count} of ${total}${president ? " (president)" : ""}`}
          >
            <span className="obar__label">
              {slice.count >= 3 || (kind === "player" && slice.count >= 2) ? name : ""}
            </span>
            <span className="obar__count num">{slice.count}</span>
          </span>
        );
      })}
    </div>
  );
}

function TradeControls({
  corp,
  options,
  explain,
  busy,
  onAct,
}: {
  corp: CorporationState;
  options: CorpTradeOptions;
  explain: boolean;
  busy: boolean;
  onAct: (action: Action) => void;
}) {
  const parBuys = options.ipoBuys.filter((a) => a.par);
  const ipoBuy = options.ipoBuys.find((a) => !a.par);
  if (parBuys.length === 0 && !ipoBuy && !options.poolBuy && options.sells.length === 0) {
    return <div className="trade trade--none">No trade</div>;
  }
  return (
    <div className="trade">
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
