"""FastAPI application. Games live in memory for the lifetime of the process."""

from __future__ import annotations

import random
import secrets
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from bby18.api.serialize import Json, board_to_json, match_action, session_to_json
from bby18.bots import GreedyBot
from bby18.board import load_board
from bby18.config import DEFAULT_CONFIG
from bby18.game import Game
from bby18.network import IllegalAction
from bby18.session import Decider, GameSession


class SeatSpec(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    bot: bool = False


class NewGameRequest(BaseModel):
    seats: list[SeatSpec] = Field(min_length=2, max_length=4)
    seed: int = 0


class ActionRequest(BaseModel):
    action: dict[str, Any]


def create_app() -> FastAPI:
    app = FastAPI(title="18BBY", version="0.1.0")
    sessions: dict[str, GameSession] = {}

    def get_session(game_id: str) -> GameSession:
        session = sessions.get(game_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"No game {game_id}")
        return session

    @app.get("/api/board")
    def board() -> Json:
        return board_to_json(load_board(DEFAULT_CONFIG.map_file))

    @app.post("/api/games")
    def new_game(request: NewGameRequest) -> Json:
        seed = request.seed or secrets.randbits(32)
        rng = random.Random(seed)
        game = Game.new([s.name for s in request.seats], DEFAULT_CONFIG)
        bots: dict[str, Decider] = {
            player.id: GreedyBot(random.Random(rng.random()))
            for player, seat in zip(game.players, request.seats)
            if seat.bot
        }
        session = GameSession(game, bots)
        session.run_bots()
        game_id = secrets.token_urlsafe(8)
        sessions[game_id] = session
        return {"gameId": game_id, "seed": seed, "state": session_to_json(session)}

    @app.get("/api/games/{game_id}")
    def get_game(game_id: str) -> Json:
        return session_to_json(get_session(game_id))

    @app.post("/api/games/{game_id}/actions")
    def act(game_id: str, request: ActionRequest) -> Json:
        session = get_session(game_id)
        try:
            action = match_action(session.legal_actions(), request.action)
            session.apply(action)
        except (ValueError, IllegalAction) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return session_to_json(session)

    return app


app = create_app()
