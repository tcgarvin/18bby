import { useEffect, useState } from "react";
import type { Board, GameState, NewGameResponse } from "./api";
import { ApiError, fetchBoard, fetchGame } from "./api";
import { GameScreen } from "./components/GameScreen";
import { NewGame } from "./components/NewGame";

type View =
  | { kind: "loading" }
  | { kind: "new"; notice: string | null }
  | { kind: "game"; gameId: string; state: GameState };

function gameIdFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get("game");
}

function setGameInUrl(gameId: string | null) {
  const url = new URL(window.location.href);
  if (gameId) url.searchParams.set("game", gameId);
  else url.searchParams.delete("game");
  window.history.replaceState(null, "", url);
}

export function App() {
  const [board, setBoard] = useState<Board | null>(null);
  const [view, setView] = useState<View>({ kind: "loading" });
  const [fatal, setFatal] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const loadedBoard = await fetchBoard();
        if (cancelled) return;
        setBoard(loadedBoard);
        const gameId = gameIdFromUrl();
        if (!gameId) {
          setView({ kind: "new", notice: null });
          return;
        }
        try {
          const state = await fetchGame(gameId);
          if (!cancelled) setView({ kind: "game", gameId, state });
        } catch (err) {
          if (!(err instanceof ApiError) || err.status !== 404) throw err;
          setGameInUrl(null);
          if (!cancelled) {
            setView({ kind: "new", notice: `Game ${gameId} is not on the server (games live in memory and end when it restarts).` });
          }
        }
      } catch (err) {
        if (!cancelled) setFatal(err instanceof Error ? err.message : String(err));
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  function created(response: NewGameResponse) {
    setGameInUrl(response.gameId);
    setView({ kind: "game", gameId: response.gameId, state: response.state });
  }

  function leave() {
    setGameInUrl(null);
    setView({ kind: "new", notice: null });
  }

  if (fatal) {
    return (
      <div className="newgame">
        <div className="newgame__card">
          <h1>Cannot reach the 18BBY server</h1>
          <p className="error">{fatal}</p>
          <p className="muted">
            Start the API with <code>uv run bby18 serve --port 8000</code> and reload.
          </p>
        </div>
      </div>
    );
  }
  if (view.kind === "loading" || board === null) return <div className="loading">Loading…</div>;
  if (view.kind === "new") return <NewGame onCreated={created} notice={view.notice} />;
  return <GameScreen key={view.gameId} gameId={view.gameId} board={board} initialState={view.state} onLeave={leave} />;
}
