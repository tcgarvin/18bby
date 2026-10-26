import { useEffect, useState } from "react";
import type { GameSummary } from "../api";
import { ApiError, deleteGame, listGames } from "../api";

interface SavedGamesProps {
  onOpen: (gameId: string) => void;
}

const PHASE_NAMES: Record<GameSummary["phase"], string> = {
  stock: "stock round",
  network: "operating round",
  fleet: "operating round",
  dividend: "operating round",
  game_over: "finished",
};

function describe(game: GameSummary): string {
  if (game.phase === "game_over") return "Finished";
  return `${game.roundLabel} · ${PHASE_NAMES[game.phase]}`;
}

function when(iso: string): string {
  const date = new Date(iso);
  const sameDay = date.toDateString() === new Date().toDateString();
  return sameDay
    ? date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
    : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** The signed-in user's saved games, with resume and delete. Renders nothing when there are none. */
export function SavedGames({ onOpen }: SavedGamesProps) {
  const [games, setGames] = useState<GameSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listGames().then(
      (loaded) => !cancelled && setGames(loaded),
      (err: unknown) => !cancelled && setError(err instanceof Error ? err.message : String(err)),
    );
    return () => {
      cancelled = true;
    };
  }, []);

  async function remove(gameId: string) {
    setConfirming(null);
    try {
      await deleteGame(gameId);
      setGames((current) => current?.filter((g) => g.gameId !== gameId) ?? null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  if (error) {
    return (
      <div className="newgame__card saved">
        <p className="error">Could not load your games: {error}</p>
      </div>
    );
  }
  if (games === null || games.length === 0) return null;
  return (
    <div className="newgame__card saved">
      <p className="eyebrow">Your games</p>
      <ul className="saved__list">
        {games.map((game) => (
          <li key={game.gameId} className="saved__game">
            <button type="button" className="saved__open" onClick={() => onOpen(game.gameId)}>
              <span className="saved__players">{game.players.map((p) => p.name).join(", ")}</span>
              <span className="saved__meta">
                {describe(game)} · {when(game.updatedAt)}
              </span>
            </button>
            {confirming === game.gameId ? (
              <span className="saved__confirm">
                <button type="button" className="link link--danger" onClick={() => void remove(game.gameId)}>
                  delete
                </button>
                <button type="button" className="link" onClick={() => setConfirming(null)}>
                  keep
                </button>
              </span>
            ) : (
              <button type="button" className="link" onClick={() => setConfirming(game.gameId)}>
                delete…
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
