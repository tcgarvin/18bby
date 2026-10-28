import type { GameState, PlayerState } from "../api";
import { corpColor } from "../selectors";
import { Ticker } from "../playback/Ticker";
import { CertStack } from "./CertStack";
import { Help } from "./Help";

interface PlayerStripProps {
  state: GameState;
  /** A one-line strip of names and cash, for views where the players are not the focus. */
  compact?: boolean;
}

/** The badge text for a bot seat: its difficulty when it has one. */
export function botLabel(difficulty: string): string {
  return difficulty ? `${difficulty} bot` : "bot";
}

/** The player whose move it is: the stock round's actor, or the operating corporation's president. */
function actingPlayer(state: GameState): string | null {
  return state.phase === "game_over" ? null : state.currentPlayer;
}

/** One card per player: cash, worth, certificates and holdings. Animation anchors: data-player-id, data-cash-for. */
export function PlayerStrip({ state, compact = false }: PlayerStripProps) {
  const acting = actingPlayer(state);
  if (compact) {
    return (
      <ul className="pstrip pstrip--compact" aria-label="Players">
        {state.players.map((p) => (
          <li key={p.id} data-player-id={p.id} className={`pchip${p.id === acting ? " pchip--acting" : ""}`}>
            <span className="pchip__name">{p.name}</span>
            <span className="pchip__cash num" data-cash-for={p.id}>
              <Ticker value={p.cash} />
            </span>
          </li>
        ))}
      </ul>
    );
  }
  return (
    <ul className="pstrip" aria-label="Players">
      {state.players.map((p, index) => (
        <PlayerCard key={p.id} state={state} player={p} acting={p.id === acting} explain={index === 0} />
      ))}
    </ul>
  );
}

interface PlayerCardProps {
  state: GameState;
  player: PlayerState;
  acting: boolean;
  /** Show the glossary "?" on the stat labels (only the first card, so the strip stays calm). */
  explain: boolean;
}

function PlayerCard({ state, player, acting, explain }: PlayerCardProps) {
  const holdings = state.corporations.filter((c) => (player.shares[c.id] ?? 0) > 0);
  const priority = state.phase === "stock" && player.id === state.priorityPlayer;
  const limit = state.config.certificateLimit;
  return (
    <li data-player-id={player.id} className={`pcard${acting ? " pcard--acting" : ""}`}>
      <div className="pcard__head">
        <span className="pcard__name">{player.name}</span>
        {player.isBot && <span className="badge">{botLabel(player.difficulty)}</span>}
        {priority && (
          <span className="badge badge--priority" title="Priority deal: acts first in the stock round">
            Priority
          </span>
        )}
        {acting && (
          <span className={`pcard__turn${state.phase === "stock" ? "" : " pcard__turn--operating"}`}>
            {state.phase === "stock" ? "to act" : "operating"}
          </span>
        )}
      </div>
      <dl className="pcard__stats">
        <div>
          <dt>Cash</dt>
          <dd className="num pcard__cash" data-cash-for={player.id}>
            <Ticker value={player.cash} />
          </dd>
        </div>
        <div>
          <dt>
            Worth
            {explain && <Help topic="netWorth" />}
          </dt>
          <dd className="num">
            <Ticker value={player.worth} />
          </dd>
        </div>
        <div>
          <dt>
            Certs
            {explain && <Help topic="certificate" />}
          </dt>
          <dd className={`num${player.certificates >= limit ? " pcard__full" : ""}`}>
            {player.certificates}
            <span className="pcard__limit">/{limit}</span>
          </dd>
        </div>
      </dl>
      <div className="pcard__holdings">
        {holdings.length === 0 && <span className="muted">No shares</span>}
        {holdings.map((corp) => (
          <CertStack
            key={corp.id}
            corpId={corp.id}
            color={corpColor(state, corp.id)}
            shares={player.shares[corp.id] ?? 0}
            president={corp.president === player.id}
          />
        ))}
      </div>
    </li>
  );
}
