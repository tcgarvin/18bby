import { useEffect, useState } from "react";
import type { Board, GameState, NewGameResponse } from "./api";
import { ApiError, fetchBoard, fetchGame } from "./api";
import { GameScreen } from "./components/GameScreen";
import { NewGame } from "./components/NewGame";
import { SavedGames } from "./components/SavedGames";

type View =
  | { kind: "loading" }
  | { kind: "new"; notice: string | null }
  | { kind: "game"; gameId: string; state: GameState };

function gameIdFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get("game");
}

/** Load a saved game, or explain on the home screen why it cannot be opened. */
async function openGame(gameId: string): Promise<View> {
  try {
    const state = await fetchGame(gameId);
    setGameInUrl(gameId);
    return { kind: "game", gameId, state };
  } catch (err) {
    if (!(err instanceof ApiError) || (err.status !== 404 && err.status !== 409)) throw err;
    setGameInUrl(null);
    const notice =
      err.status === 404
        ? `Game ${gameId} was not found. It may have been deleted, or started in another browser.`
        : err.message;
    return { kind: "new", notice };
  }
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
        const opened = await openGame(gameId);
        if (!cancelled) setView(opened);
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

  async function open(gameId: string) {
    try {
      setView(await openGame(gameId));
    } catch (err) {
      setFatal(err instanceof Error ? err.message : String(err));
    }
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
          {import.meta.env.DEV && (
            <p className="muted">
              Start the API with <code>uv run bby18 serve --port 8000</code> and reload.
            </p>
          )}
        </div>
      </div>
    );
  }
  if (view.kind === "loading" || board === null) return <div className="loading">Loading…</div>;
  if (view.kind === "new") {
    return (
      <div className="newgame newgame--home">
        <SavedGames onOpen={(gameId) => void open(gameId)} />
        <NewGame onCreated={created} notice={view.notice} />
      </div>
    );
  }
  return <GameScreen key={view.gameId} gameId={view.gameId} board={board} initialState={view.state} onLeave={leave} />;
}
