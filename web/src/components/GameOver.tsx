import type { GameState } from "../api";
import { corpColor } from "../selectors";
import { CertStack } from "./CertStack";
import { DeathStarGlyph } from "./DeathStar";
import { botLabel } from "./PlayerStrip";

/** Players ranked by final worth, each with their holdings and (for bots) the plan they played. */
export function GameOver({ state, onNewGame }: { state: GameState; onNewGame: () => void }) {
  const ranking = [...state.players].sort((a, b) => b.worth - a.worth);
  const deathStar = state.deathStar;
  const closed = state.corporations.filter((c) => c.status === "closed").map((c) => c.id);
  return (
    <div className="final">
      {deathStar && (
        <p className="final__ending">
          <DeathStarGlyph size={18} />
          <span>
            {deathStar.launched
              ? `The Death Star launched: the Battle of Yavin ended the game after round ${deathStar.finalRound}.`
              : `The station was never finished: the game ended at the round ${deathStar.finalRound} backstop.`}
            {closed.length > 0 && ` Bankrupt, shares worthless: ${closed.join(", ")}.`}
          </span>
        </p>
      )}
      <p className="final__lead">Final worth is cash plus shares at market price.</p>
      <ol className="ranking">
        {ranking.map((p, i) => (
          <li key={p.id} data-player-id={p.id} className={i === 0 ? "ranking__winner" : ""}>
            <span className="ranking__place">{i + 1}</span>
            <span className="ranking__who">
              <span className="ranking__name">
                {p.name}
                {p.isBot && <span className="badge">{botLabel(p.difficulty)}</span>}
              </span>
              <span className="ranking__detail">
                cash <span className="num" data-cash-for={p.id}>{p.cash}</span>
                {state.corporations
                  .filter((c) => (p.shares[c.id] ?? 0) > 0)
                  .map((c) => (
                    <CertStack
                      key={c.id}
                      corpId={c.id}
                      color={corpColor(state, c.id)}
                      shares={p.shares[c.id] ?? 0}
                      president={c.president === p.id}
                    />
                  ))}
              </span>
              {p.plan && <span className="ranking__plan">Played to {p.plan}.</span>}
            </span>
            <span className="ranking__worth num">{p.worth}</span>
          </li>
        ))}
      </ol>
      <button type="button" className="btn btn--primary" onClick={onNewGame}>
        New game
      </button>
    </div>
  );
}
