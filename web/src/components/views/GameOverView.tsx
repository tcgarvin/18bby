import { GameOver } from "../GameOver";
import { Help } from "../Help";
import { MapThumbnail } from "../MapThumbnail";
import { StockMarket } from "../StockMarket";
import type { ViewProps } from "./types";

interface GameOverViewProps extends ViewProps {
  onNewGame: () => void;
}

/** Final standings, with the closing market and map alongside. */
export function GameOverView({ state, board, onOpen, onNewGame }: GameOverViewProps) {
  return (
    <div className="view view--over">
      <section className="panel standings">
        <h2 className="panel__title">Final standings</h2>
        <GameOver state={state} onNewGame={onNewGame} />
      </section>
      <section className="panel stockmarket">
        <h2 className="panel__title">
          Closing market
          <Help topic="marketMovement" />
        </h2>
        <StockMarket state={state} />
      </section>
      <section className="panel stockmap">
        <MapThumbnail state={state} board={board} onOpen={() => onOpen("map")} />
      </section>
    </div>
  );
}
