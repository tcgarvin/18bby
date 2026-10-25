"""FastAPI application.

Each request loads its game from the ``GameStore``, acts on it and writes it back, so the API
holds no game state between requests and can run as a serverless function. Games belong to the
user the ``Authenticator`` identifies; someone else's game answers 404, as if it did not exist.

``bby18.api.main:app`` is the instance configured from the environment (``settings_from_env``).
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, replace
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, model_validator

from bby18.api.auth import (
    AuthError,
    Authenticator,
    FixedUserAuthenticator,
    TokenAuthenticator,
    create_account,
)
from bby18.api.saves import (
    CODE_VERSION,
    SaveOutdated,
    apply_submitted,
    bot_seats,
    load_session,
    new_session,
    replay,
    snapshot,
)
from bby18.api.serialize import Json, board_to_json, rules_to_json, session_to_json
from bby18.api.store import (
    AccountStore,
    GameNotFound,
    GameStore,
    MemoryStore,
    PostgresStore,
    SavedGame,
    Seat,
    StaleSave,
)
from bby18.board import load_board
from bby18.bots.roster import DIFFICULTIES, PLANS, character_named
from bby18.config import DEFAULT_CONFIG
from bby18.network import IllegalAction
from bby18.session import GameSession, Phase

LOCAL_USER = "local"
FRONTEND_DIRECTORY = "public"


class SeatSpec(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    bot: bool = False
    difficulty: str = ""
    """For a bot seat: a roster difficulty, and the server picks a named character. Empty
    seats the original bot under the given name."""

    @model_validator(mode="after")
    def _check_difficulty(self) -> SeatSpec:
        if self.difficulty and not self.bot:
            raise ValueError("Only bot seats take a difficulty")
        if self.difficulty and self.difficulty not in DIFFICULTIES:
            raise ValueError(f"Unknown difficulty {self.difficulty!r}; choose from {DIFFICULTIES}")
        return self


class NewGameRequest(BaseModel):
    seats: list[SeatSpec] = Field(min_length=2, max_length=4)
    seed: int | None = Field(default=None, ge=0, lt=2**63)
    """Omit for a random seed. Any integer, including 0, is honored."""


class ActionRequest(BaseModel):
    action: dict[str, Any]


def create_app(store: GameStore, accounts: AccountStore, authenticator: Authenticator) -> FastAPI:
    app = FastAPI(title="18BBY", version="0.1.0")

    def current_user(authorization: Annotated[str, Header()] = "") -> str:
        try:
            return authenticator.user_id(authorization)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def load(user: str, game_id: str) -> tuple[SavedGame, GameSession]:
        try:
            saved = store.get(user, game_id)
            return saved, load_session(saved)
        except GameNotFound as exc:
            raise HTTPException(status_code=404, detail=f"No game {game_id}") from exc
        except SaveOutdated as exc:
            raise HTTPException(
                status_code=409,
                detail=f"This game was saved under older rules and cannot be resumed. {exc}",
            ) from exc

    def write(saved: SavedGame, actions: tuple[Json, ...], session: GameSession) -> Json:
        try:
            saved = store.update(_with_session(saved, actions, session))
        except StaleSave as exc:
            raise HTTPException(
                status_code=409,
                detail="This game was changed elsewhere (another tab?). Reload to continue.",
            ) from exc
        return _state_json(saved, session)

    @app.post("/api/accounts")
    def new_account() -> Json:
        """A new anonymous account. The token is shown only here; the browser must keep it."""
        account = create_account(accounts)
        return {"accountId": account.account_id, "token": account.token}

    @app.get("/api/board")
    def board() -> Json:
        return board_to_json(load_board(DEFAULT_CONFIG.map_file))

    @app.get("/api/rules")
    def rules() -> Json:
        """The tunable numbers behind the rules page; public, like the board."""
        return rules_to_json(DEFAULT_CONFIG)

    @app.get("/api/games")
    def list_games(user: str = Depends(current_user)) -> Json:
        return {
            "games": [
                {
                    "gameId": g.id,
                    "players": [{"name": s.name, "bot": s.bot} for s in g.seats],
                    "phase": g.phase,
                    "roundLabel": g.round_label,
                    "updatedAt": g.updated_at.isoformat(),
                }
                for g in store.list_for_owner(user)
            ]
        }

    @app.post("/api/games")
    def new_game(request: NewGameRequest, user: str = Depends(current_user)) -> Json:
        seed = request.seed if request.seed is not None else secrets.randbits(32)
        seats = bot_seats(
            seed, (Seat(name=s.name, bot=s.bot, difficulty=s.difficulty) for s in request.seats)
        )
        session = new_session(seed, seats)
        saved = SavedGame(
            id=secrets.token_urlsafe(8),
            owner=user,
            seed=seed,
            seats=seats,
            actions=(),
            code_version=CODE_VERSION,
            snapshot=snapshot(session),
            phase=session.phase.value,
            round_label=session.game.round_label,
        )
        store.create(saved)
        return {"gameId": saved.id, "seed": seed, "state": _state_json(saved, session)}

    @app.get("/api/games/{game_id}")
    def get_game(game_id: str, user: str = Depends(current_user)) -> Json:
        saved, session = load(user, game_id)
        return _state_json(saved, session)

    @app.post("/api/games/{game_id}/actions")
    def act(game_id: str, request: ActionRequest, user: str = Depends(current_user)) -> Json:
        saved, session = load(user, game_id)
        try:
            apply_submitted(session, request.action)
        except (ValueError, IllegalAction) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return write(saved, (*saved.actions, request.action), session)

    @app.post("/api/games/{game_id}/undo")
    def undo(game_id: str, user: str = Depends(current_user)) -> Json:
        saved, _ = load(user, game_id)
        if not saved.actions:
            raise HTTPException(status_code=400, detail="Nothing to undo")
        actions = saved.actions[:-1]
        return write(saved, actions, replay(saved.seed, saved.seats, actions))

    @app.delete("/api/games/{game_id}", status_code=204)
    def delete_game(game_id: str, user: str = Depends(current_user)) -> None:
        try:
            store.delete(user, game_id)
        except GameNotFound as exc:
            raise HTTPException(status_code=404, detail=f"No game {game_id}") from exc

    return app


def _with_session(saved: SavedGame, actions: tuple[Json, ...], session: GameSession) -> SavedGame:
    return replace(
        saved,
        actions=actions,
        code_version=CODE_VERSION,
        snapshot=snapshot(session),
        phase=session.phase.value,
        round_label=session.game.round_label,
    )


def _state_json(saved: SavedGame, session: GameSession) -> Json:
    state = session_to_json(session)
    over = session.phase is Phase.GAME_OVER
    # Players are listed in seat order. A character's strategy stays hidden until the end.
    for player, seat in zip(state["players"], saved.seats):
        player["difficulty"] = seat.difficulty
        player["plan"] = (
            PLANS[character_named(seat.character).strategy] if over and seat.character else ""
        )
    # Undo replays the save without its last action, so it is available whenever there is one.
    return {**state, "canUndo": bool(saved.actions)}


@dataclass(frozen=True)
class Settings:
    mode: str
    """``local``: in-memory games and a single local user. ``postgres``: the deployed setup."""
    database_url: str = ""


def settings_from_env() -> Settings:
    """Read ``BBY18_MODE`` and, in postgres mode, ``DATABASE_URL``.

    There is no default mode, so a deployment that forgets its configuration fails at startup
    instead of quietly serving unauthenticated, unsaved games.
    """
    mode = os.environ.get("BBY18_MODE", "")
    if mode == "local":
        return Settings(mode=mode)
    if mode == "postgres":
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url:
            raise RuntimeError("BBY18_MODE=postgres needs DATABASE_URL")
        return Settings(mode=mode, database_url=database_url)
    raise RuntimeError(f"Set BBY18_MODE to 'local' or 'postgres' (got {mode!r})")


def app_from_settings(settings: Settings) -> FastAPI:
    if settings.mode == "local":
        memory = MemoryStore()
        return create_app(memory, memory, FixedUserAuthenticator(LOCAL_USER))
    store = PostgresStore(settings.database_url)
    # The deployed database URL is a sensitive value that cannot be read outside the platform,
    # so the server brings the schema up to date itself; it is idempotent and cheap.
    store.migrate()
    app = create_app(store, store, TokenAuthenticator(store))
    # The deploy build writes the frontend to public/. Vercel serves those files from its CDN and
    # leaves them out of the function bundle, so the directory is absent at runtime and must not
    # be checked; declaring it is what tells Vercel to publish it. API routes take precedence.
    app.frontend("/", directory=FRONTEND_DIRECTORY, check_dir=False)
    return app
