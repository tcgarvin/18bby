import type { GameState } from "../api";
import { corporationColor } from "../colors";
import { Help } from "./Help";

export function PlayersPanel({ state }: { state: GameState }) {
  const corpIds = state.corporations.map((c) => c.id);
  const acting = state.phase === "stock" ? state.currentPlayer : null;
  const president = state.phase === "network" || state.phase === "dividend" ? state.currentPlayer : null;
  return (
    <section className="panel">
      <h2 className="panel__title">Players</h2>
      <table className="grid-table">
        <thead>
          <tr>
            <th>Player</th>
            <th className="num">Cash</th>
            <th className="num">
              Worth
              <Help topic="netWorth" />
            </th>
            <th>Shares</th>
            <th className="num" title="Certificates held / limit">
              Certs
              <Help topic="certificate" />
            </th>
          </tr>
        </thead>
        <tbody>
          {state.players.map((p) => (
            <tr key={p.id} className={p.id === acting || p.id === president ? "is-current" : ""}>
              <td>
                <span className="player-name">
                  {p.name}
                  {p.isBot && <span className="badge">bot</span>}
                  {state.phase === "stock" && p.id === state.priorityPlayer && (
                    <span className="badge badge--priority" title="Priority deal">
                      PD
                    </span>
                  )}
                </span>
              </td>
              <td className="num">{p.cash}</td>
              <td className="num">{p.worth}</td>
              <td>
                <span className="share-list">
                  {Object.entries(p.shares).map(([corpId, count]) => (
                    <span key={corpId} className="share" style={{ borderColor: corporationColor(corpId, corpIds) }}>
                      <span className="share__id" style={{ color: corporationColor(corpId, corpIds) }}>
                        {corpId}
                      </span>
                      <span className="num">{count * 10}%</span>
                    </span>
                  ))}
                </span>
              </td>
              <td className="num">
                {p.certificates}/{state.config.certificateLimit}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
