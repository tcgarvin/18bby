import { useHotkeys } from "../../hotkeys";
import { playerName } from "../../selectors";
import { CorporationBoard } from "../CorporationBoard";
import { Help } from "../Help";
import { MapThumbnail } from "../MapThumbnail";
import { PlayerStrip } from "../PlayerStrip";
import { StockMarket } from "../StockMarket";
import type { ViewProps } from "./types";

/**
 * Who has what and what is for sale: players, corporations with inline trades, and the market.
 * Browsed outside the stock round it is the Shares view: the same cards and market without
 * trades, Pass or buy blocks.
 */
export function StockRoundView({ state, board, interactive, browsing, busy, keyboard, onAct, onView }: ViewProps) {
  const pass = interactive ? state.legalActions.find((a) => a.type === "pass") : undefined;
  useHotkeys({ p: () => (pass && !busy ? onAct(pass) : false) }, interactive && keyboard);
  const who = playerName(state, state.currentPlayer);

  return (
    <div className="view view--stock">
      <PlayerStrip state={state} />

      <section className={`panel stockboard${interactive ? " stockboard--yours" : ""}${browsing ? " stockboard--browse" : ""}`}>
        <header className="stockboard__head">
          <div className="stockboard__prompt">
            {browsing ? (
              <span className="stockboard__title">Corporations</span>
            ) : interactive ? (
              <>
                <strong>{who}, your turn.</strong> Buy one share, sell, or pass.
                <Help topic="stockRound" />
              </>
            ) : (
              <span className="muted">{who} is deciding…</span>
            )}
          </div>
          {pass && (
            <button type="button" className="btn btn--primary btn--pass" disabled={busy} onClick={() => onAct(pass)}>
              <span>
                Pass <kbd>P</kbd>
              </span>
            </button>
          )}
        </header>
        <div className="stockboard__body">
          <CorporationBoard state={state} interactive={interactive} busy={busy} onAct={onAct} />
        </div>
      </section>

      <section className="panel stockmarket">
        <h2 className="panel__title">
          Stock market
          <Help topic="marketMovement" />
          <span className="panel__aside">pay → right · withhold ← left · sell ↓ · sold out ↑</span>
        </h2>
        <StockMarket state={state} />
      </section>

      <section className="panel stockmap">
        <MapThumbnail state={state} board={board} onOpen={() => onView("map")} />
      </section>
    </div>
  );
}
