import type { GameState } from "../api";
import { botLabel } from "./PlayersPanel";

export function GameOver({ state, onNewGame }: { state: GameState; onNewGame: () => void }) {
  const ranking = [...state.players].sort((a, b) => b.worth - a.worth);
  return (
    <div className="actions">
      <p className="actions__lead">Game over. Final worth is cash plus shares at market price.</p>
      <ol className="ranking">
        {ranking.map((p, i) => (
          <li key={p.id} className={i === 0 ? "ranking__winner" : ""}>
            <span className="ranking__place">{i + 1}</span>
            <span>
              {p.name}
              {p.isBot && <span className="badge">{botLabel(p.difficulty)}</span>}
              {p.plan && <span className="ranking__plan">Played to {p.plan}.</span>}
            </span>
            <span className="num">{p.worth}</span>
          </li>
        ))}
      </ol>
      <button type="button" className="btn btn--primary" onClick={onNewGame}>
        New game
      </button>
    </div>
  );
}
