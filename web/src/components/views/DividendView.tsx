import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { Action, Axial, Board, CorporationState, DividendAction, GameState } from "../../api";
import { pairUsage, pairUsageText, sitePlanet } from "../../deathstar";
import { supplyItem } from "../../facilities";
import { useHotkeys } from "../../hotkeys";
import { useSettled } from "../../playback/useSettled";
import { corpColor, dividendSplit, findCorporation, nearestCellWithPrice, playerName, terrainByKey } from "../../selectors";
import { CertStack } from "../CertStack";
import { Help } from "../Help";
import { HexMap } from "../HexMap";
import { OperatingRail } from "../OperatingRail";
import { PlayerStrip } from "../PlayerStrip";
import { StockMarket } from "../StockMarket";
import type { MarketGhost, MarketWindow } from "../StockMarket";
import type { ViewProps } from "./types";

const NO_HEXES = new Set<string>();
const HOTKEY: Record<DividendAction["choice"], string> = { pay: "1", withhold: "2" };

/**
 * The operating corporation's revenue and the choice to pay it out or keep it, with the map
 * shrunk to the corporation's network so its scored routes show.
 */
export function DividendView({ state, board, interactive, busy, keyboard, changedHexes, replayStep, onAct }: ViewProps) {
  const [explicitFocus, setExplicitFocus] = useState<string | null>(null);
  const turn = `${state.roundLabel}:${state.currentCorporation}`;
  const [focusTurn, setFocusTurn] = useState(turn);
  if (turn !== focusTurn) {
    setFocusTurn(turn);
    setExplicitFocus(null);
  }
  const corp = findCorporation(state, state.currentCorporation);
  // Replaying an opponent's dividend: the cards show the figures it decided on (the game before
  // the move), with its choice marked, while the market token moves to the new price.
  const decided = replayStep?.kind.kind === "dividend" ? replayStep : null;
  const chosen: DividendAction["choice"] | null =
    decided?.kind.kind === "dividend" ? (decided.kind.pay ? "pay" : "withhold") : null;
  const decisionState = decided ? decided.before : state;
  const decisionCorp = findCorporation(decisionState, state.currentCorporation) ?? corp;
  const focusCorp = explicitFocus ?? state.currentCorporation;
  const focus = findCorporation(state, focusCorp);
  const terrain = useMemo(() => terrainByKey(state.terrain), [state.terrain]);
  const choices = interactive ? state.legalActions.filter((a): a is DividendAction => a.type === "dividend") : [];
  useHotkeys(
    Object.fromEntries(choices.map((action) => [HOTKEY[action.choice], () => (busy ? false : onAct(action))])),
    interactive && keyboard,
  );
  if (!corp || !decisionCorp) return null;

  return (
    <div className="view view--operating view--dividend">
      <div className="dividend">
        <PlayerStrip state={state} compact />
        <Decision
          state={decisionState}
          marketState={state}
          corp={decisionCorp}
          choices={choices}
          chosen={chosen}
          interactive={interactive}
          busy={busy}
          onAct={onAct}
        />
        <section className="panel revenue" style={{ ["--corp" as string]: corpColor(state, corp.id) }}>
          <div className="revenue__map">
            <HexMap
              board={board}
              tiles={state.tiles}
              terrain={terrain}
              nebulaChartSurcharge={state.config.nebulaChartSurcharge}
              corporations={state.corporations}
              focusCorp={focusCorp}
              actionableHexes={NO_HEXES}
              selectedHex={null}
              preview={null}
              changedHexes={changedHexes}
              onHexClick={() => undefined}
              fitHexes={focus ? networkHexes(state, board, focus) : undefined}
              label={`${focusCorp ?? ""} network`}
              deathStar={state.deathStar}
              facilities={state.facilities}
            />
          </div>
          {focus && <RevenueBreakdown state={state} corp={focus} />}
        </section>
      </div>

      <OperatingRail
        state={state}
        focusCorp={focusCorp}
        onFocus={(id) => setExplicitFocus((current) => (current === id || id === state.currentCorporation ? null : id))}
      >
        <p className="netpanel__hint">
          {interactive ? (
            <>
              Earns <strong className="num">{corp.revenue.total}</strong>: pay it to shareholders or keep it in the
              treasury.
            </>
          ) : chosen ? (
            <>
              {playerName(state, corp.president)} {chosen === "pay" ? "pays it out" : "keeps it in the treasury"}.
            </>
          ) : (
            <>{playerName(state, corp.president)} is deciding whether to pay or withhold…</>
          )}
        </p>
      </OperatingRail>
    </div>
  );
}

/** Hexes the corporation's network touches: served tiles, reachable planets and its homeworld. */
function networkHexes(state: GameState, board: Board, corp: CorporationState): Axial[] {
  const names = new Set([...corp.reachablePlanets, corp.homeworld]);
  const site = sitePlanet(state.deathStar);
  const hubs = site ? [...board.planets, site] : board.planets;
  return [
    ...state.tiles.filter((t) => t.service.includes(corp.id)).map((t) => t.hex),
    ...hubs.filter((p) => names.has(p.name)).map((p) => p.hex),
  ];
}

interface DecisionProps {
  /** The game the decision is made in: figures, payouts and price previews come from here. */
  state: GameState;
  /** Where the market tokens stand now; differs from `state` while a decision replays. */
  marketState: GameState;
  corp: CorporationState;
  choices: DividendAction[];
  /** The choice an opponent made, marked while it replays; null otherwise. */
  chosen: DividendAction["choice"] | null;
  interactive: boolean;
  busy: boolean;
  onAct: (action: Action) => void;
}

function Decision({ state, marketState, corp, choices, chosen, interactive, busy, onAct }: DecisionProps) {
  const tokens = useSettled(state, marketState);
  const total = corp.revenue.total;
  const preview = corp.dividendPreview ?? { pay: corp.price, withhold: corp.price };
  const split = dividendSplit(state, corp, total);
  const cell = corp.marketCell;
  const payCell = cell ? nearestCellWithPrice(state.stockMarket, cell, preview.pay) : null;
  const withholdCell = cell ? nearestCellWithPrice(state.stockMarket, cell, preview.withhold) : null;
  const ghosts: MarketGhost[] = [];
  if (payCell) ghosts.push({ corpId: corp.id, cell: payCell, label: "pay", tone: tone(corp.price, preview.pay) });
  if (withholdCell) ghosts.push({ corpId: corp.id, cell: withholdCell, label: "withhold", tone: tone(corp.price, preview.withhold) });
  const window = cell ? marketWindow(state.stockMarket, [cell, ...ghosts.map((g) => g.cell)]) : undefined;
  const actionFor = (choice: DividendAction["choice"]) => choices.find((a) => a.choice === choice);

  return (
    <section className="panel decision" style={{ ["--corp" as string]: corpColor(state, corp.id) }}>
      <header className="decision__head">
        <span className="decision__corp">{corp.id}</span>
        <span className="decision__earned">
          earned <strong className="num">{total}</strong>
          <Help topic="revenue" />
        </span>
        <span className="decision__who">
          president {playerName(state, corp.president)}
          {!interactive && (chosen ? ` · chose to ${chosen}` : " · deciding")}
        </span>
      </header>

      <div className="choices">
        <ChoiceCard
          kind="pay"
          action={actionFor("pay")}
          chosen={chosen}
          busy={busy}
          onAct={onAct}
          title={`Pay ${total}`}
          subtitle={
            <>
              <strong className="num">{split.perShare}</strong> per share to shareholders
              <Help topic="dividend" />
            </>
          }
        >
          <ul className="payouts">
            {split.payouts
              .filter((p) => p.shares > 0)
              .map((p) => (
                <li key={p.playerId}>
                  <span className="payouts__name">{playerName(state, p.playerId)}</span>
                  <CertStack
                    corpId={corp.id}
                    color={corpColor(state, corp.id)}
                    shares={p.shares}
                    president={p.playerId === corp.president}
                  />
                  <span className="payouts__amount num">+{p.amount}</span>
                </li>
              ))}
            {split.bankKeeps > 0 && (
              <li className="payouts__bank">
                <span className="payouts__name">Bank keeps</span>
                {corp.ipoShares + corp.poolShares > 0 ? (
                  <CertStack
                    corpId={corp.id}
                    color={corpColor(state, corp.id)}
                    shares={corp.ipoShares + corp.poolShares}
                    title={`${corp.ipoShares + corp.poolShares} unheld shares (IPO and pool) earn nothing`}
                  />
                ) : (
                  <span className="payouts__shares">remainder</span>
                )}
                <span className="payouts__amount num">{split.bankKeeps}</span>
              </li>
            )}
          </ul>
          <Moves price={[corp.price, preview.pay]} treasury={[corp.treasury, corp.treasury]} />
        </ChoiceCard>

        <ChoiceCard
          kind="withhold"
          action={actionFor("withhold")}
          chosen={chosen}
          busy={busy}
          onAct={onAct}
          title="Withhold"
          subtitle={
            <>
              <strong className="num">{total}</strong> into the treasury, shareholders get nothing
              <Help topic="withhold" />
            </>
          }
        >
          <Moves price={[corp.price, preview.withhold]} treasury={[corp.treasury, corp.treasury + total]} />
        </ChoiceCard>
      </div>

      {window && (
        <div className="decision__market">
          <StockMarket state={tokens} window={window} ghosts={ghosts} emphasis={corp.id} fill />
        </div>
      )}
    </section>
  );
}

function tone(from: number, to: number): MarketGhost["tone"] {
  return to > from ? "up" : to < from ? "down" : "flat";
}

/** The rows and columns around some cells, with three columns of context either side. */
function marketWindow(market: number[][], cells: [number, number][]): MarketWindow {
  const width = Math.max(...market.map((row) => row.length));
  const rows = cells.map((c) => c[0]);
  const cols = cells.map((c) => c[1]);
  const clamp = (v: number, max: number) => Math.max(0, Math.min(max, v));
  return {
    rows: [clamp(Math.min(...rows) - 1, market.length - 1), clamp(Math.max(...rows) + 1, market.length - 1)],
    cols: [clamp(Math.min(...cols) - 3, width - 1), clamp(Math.max(...cols) + 3, width - 1)],
  };
}

interface ChoiceCardProps {
  kind: DividendAction["choice"];
  /** The legal action, or undefined when the view is read-only. */
  action: DividendAction | undefined;
  /** An opponent's replayed choice: that card is marked, the other faded. */
  chosen: DividendAction["choice"] | null;
  busy: boolean;
  onAct: (action: Action) => void;
  title: string;
  subtitle: ReactNode;
  children: ReactNode;
}

function ChoiceCard({ kind, action, chosen, busy, onAct, title, subtitle, children }: ChoiceCardProps) {
  const body = (
    <>
      <span className="choice__title">
        {title}
        {action && <kbd>{HOTKEY[kind]}</kbd>}
      </span>
      <span className="choice__sub">{subtitle}</span>
      <span className="choice__body">{children}</span>
    </>
  );
  if (!action) {
    const mark = chosen === null ? "" : chosen === kind ? " choice--chosen" : " choice--passed";
    return <div className={`choice choice--${kind} choice--readonly${mark}`}>{body}</div>;
  }
  return (
    // A div with role=button, not a button: the subtitle holds "?" help buttons, which cannot nest in one.
    <div
      role="button"
      tabIndex={busy ? -1 : 0}
      aria-disabled={busy}
      className={`choice choice--${kind}`}
      onClick={() => !busy && onAct(action)}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget || (event.key !== "Enter" && event.key !== " ") || busy) return;
        event.preventDefault();
        onAct(action);
      }}
    >
      {body}
    </div>
  );
}

function Moves({ price, treasury }: { price: [number, number]; treasury: [number, number] }) {
  return (
    <dl className="moves">
      <div>
        <dt>Share price</dt>
        <dd className={`num moves--${tone(price[0], price[1])}`}>
          {price[0]} → <strong>{price[1]}</strong>
        </dd>
      </div>
      <div>
        <dt>Treasury</dt>
        <dd className={`num moves--${tone(treasury[0], treasury[1])}`}>
          {treasury[0] === treasury[1] ? (
            <>{treasury[0]} (unchanged)</>
          ) : (
            <>
              {treasury[0]} → <strong>{treasury[1]}</strong>
            </>
          )}
        </dd>
      </div>
    </dl>
  );
}

/**
 * The scored pairs behind the revenue, matching the arcs on the map: solid typed, dashed basic,
 * dotted contract. Under the Death Star rules it also says how many pairs the fleets (or facilities) run.
 */
function RevenueBreakdown({ state, corp }: { state: GameState; corp: CorporationState }) {
  const { total, pairs } = corp.revenue;
  const item = supplyItem(state.deathStar);
  const usage = pairUsage(corp, item);
  const contracts = pairs.filter((p) => p.contract).length;
  const typed = pairs.filter((p) => p.typed && !p.contract).length;
  const basic = pairs.length - typed - contracts;
  return (
    <div className="revenue__pairs">
      <h3 className="revenue__title">
        <span className="chip" style={{ background: corpColor(state, corp.id) }}>
          {corp.id}
        </span>{" "}
        revenue <strong className="num">{total}</strong>
        <Help topic="revenue" />
      </h3>
      {usage && (
        <p className="revenue__usage">
          <span>{pairUsageText(usage)}</span>
          {usage.available > usage.run && <span className="muted">one pair per {item}</span>}
          <Help topic={item === "facility" ? "facility" : "fleet"} />
        </p>
      )}
      {pairs.length === 0 ? (
        <p className="muted">No scoring pairs yet.</p>
      ) : (
        <table className="pairs">
          <tbody>
            {pairs.map((pair) => (
              <tr key={`${pair.a}-${pair.b}`}>
                <td>
                  <span
                    className={`pairs__line${pair.contract ? " pairs__line--contract" : pair.typed ? "" : " pairs__line--basic"}`}
                    aria-hidden
                  />
                  {pair.a} ↔ {pair.b}
                </td>
                <td className={pair.contract ? "pairs__contract" : "muted"}>
                  {pair.contract ? "contract" : pair.typed ? "typed" : "basic"}
                </td>
                <td className="num">{pair.value}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td>Total</td>
              <td className="muted">
                {contracts > 0 && (
                  <>
                    {contracts} contract <Help topic="contract" /> ·{" "}
                  </>
                )}
                {typed} typed <Help topic="typedPair" /> · {basic} basic <Help topic="basicRoute" />
              </td>
              <td className="num">{total}</td>
            </tr>
          </tfoot>
        </table>
      )}
      {contracts > 0 && (
        <p className="revenue__usage">
          Paid or withheld, {contracts === 1 ? "the contract adds a cube" : `the contracts add ${contracts} cubes`} to the Death
          Star track.
        </p>
      )}
    </div>
  );
}
