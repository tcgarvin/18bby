import { useEffect, useState } from "react";
import type { Board, GameState, NewGameResponse, Rules } from "./api";
import { ApiError, fetchBoard, fetchGame, fetchRules } from "./api";
import { GameScreen } from "./components/GameScreen";
import { NewGame } from "./components/NewGame";
import { RulesPage } from "./components/RulesPage";
import { SavedGames } from "./components/SavedGames";
import { SECTION_IDS } from "./help/glossary";
import type { SectionId } from "./help/glossary";
import { RulesProvider } from "./help/rulesContext";

type View =
  | { kind: "loading" }
  | { kind: "new"; notice: string | null }
  | { kind: "game"; gameId: string; state: GameState };

function gameIdFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get("game");
}

/** The rules page is requested as ``?rules`` or ``?rules=<section>``; null means a normal visit. */
function rulesRequest(): { section: SectionId | null } | null {
  const params = new URLSearchParams(window.location.search);
  if (!params.has("rules")) return null;
  const section = params.get("rules");
  return { section: SECTION_IDS.find((id) => id === section) ?? null };
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
  const [rules, setRules] = useState<Rules | null>(null);
  const [view, setView] = useState<View>({ kind: "loading" });
  const [fatal, setFatal] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const loadedRules = await fetchRules();
        if (cancelled) return;
        setRules(loadedRules);
        if (rulesRequest()) return;
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
  if (rules === null) return <div className="loading">Loading…</div>;
  const requested = rulesRequest();
  if (requested) {
    return (
      <RulesProvider value={rules}>
        <RulesPage section={requested.section} />
      </RulesProvider>
    );
  }
  if (view.kind === "loading" || board === null) return <div className="loading">Loading…</div>;
  if (view.kind === "new") {
    return (
      <RulesProvider value={rules}>
        <div className="newgame newgame--home">
          <SavedGames onOpen={(gameId) => void open(gameId)} />
          <NewGame onCreated={created} notice={view.notice} />
        </div>
      </RulesProvider>
    );
  }
  return (
    <RulesProvider value={rules}>
      <GameScreen key={view.gameId} gameId={view.gameId} board={board} initialState={view.state} onLeave={leave} />
    </RulesProvider>
  );
}
