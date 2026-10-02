"""Where accounts and saved games live between requests.

The API keeps nothing in memory between requests: every request loads the game it needs from a
``GameStore`` and writes it back after a change. ``MemoryStore`` backs tests and local play;
``PostgresStore`` is the deployed store (Neon), with its schema in ``schema.sql``.

Each save carries a ``revision`` that goes up by one on every write. A write names the revision
it started from and fails with ``StaleSave`` if someone else wrote first, so a second browser
tab on an old position cannot overwrite newer moves.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from importlib.resources import files
from typing import Any, Protocol

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Jsonb

Json = dict[str, Any]


class GameNotFound(Exception):
    """No game with this id belongs to this owner."""


class AccountNotFound(Exception):
    """No account has this token."""


class StaleSave(Exception):
    """The game changed since it was loaded; the write was refused."""


class StoreError(Exception):
    """The store failed for a reason other than not-found or a stale write."""


@dataclass(frozen=True)
class Seat:
    name: str
    bot: bool


@dataclass(frozen=True)
class SavedGame:
    """Everything needed to resume a game.

    ``seed``, ``seats`` and ``actions`` are the durable record: replaying the submitted
    actions from the seed rebuilds the game. ``snapshot`` is a cached copy of the resulting
    session, valid only while ``code_version`` matches the running engine.
    """

    id: str
    owner: str
    seed: int
    seats: tuple[Seat, ...]
    actions: tuple[Json, ...]
    code_version: str
    snapshot: bytes
    phase: str
    round_label: str
    revision: int = 0
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class GameSummary:
    """What the list of a player's games shows, without the heavy save columns."""

    id: str
    seats: tuple[Seat, ...]
    phase: str
    round_label: str
    updated_at: datetime


class AccountStore(Protocol):
    def create_account(self, account_id: str, token_hash: str) -> None: ...

    def account_for_token(self, token_hash: str) -> str:
        """The id of the account with this token hash. Raises AccountNotFound."""
        ...


class GameStore(Protocol):
    def create(self, game: SavedGame) -> None: ...

    def get(self, owner: str, game_id: str) -> SavedGame:
        """Raises GameNotFound when the game does not exist or belongs to someone else."""
        ...

    def update(self, game: SavedGame) -> SavedGame:
        """Write ``game`` over the save at ``game.revision``; return it at the next revision.

        Raises StaleSave when the stored revision has moved on.
        """
        ...

    def list_for_owner(self, owner: str) -> list[GameSummary]:
        """The owner's games, most recently played first."""
        ...

    def delete(self, owner: str, game_id: str) -> None: ...


class MemoryStore:
    """A process-local store for tests and local play. Everything ends with the process."""

    def __init__(self) -> None:
        self._accounts: dict[str, str] = {}
        """Token hash to account id."""
        self._games: dict[str, SavedGame] = {}

    def create_account(self, account_id: str, token_hash: str) -> None:
        if token_hash in self._accounts or account_id in self._accounts.values():
            raise StoreError("Account already exists")
        self._accounts[token_hash] = account_id

    def account_for_token(self, token_hash: str) -> str:
        account_id = self._accounts.get(token_hash)
        if account_id is None:
            raise AccountNotFound()
        return account_id

    def create(self, game: SavedGame) -> None:
        if game.id in self._games:
            raise StoreError(f"Game {game.id} already exists")
        self._games[game.id] = game

    def get(self, owner: str, game_id: str) -> SavedGame:
        game = self._games.get(game_id)
        if game is None or game.owner != owner:
            raise GameNotFound(game_id)
        return game

    def update(self, game: SavedGame) -> SavedGame:
        current = self._games.get(game.id)
        if current is None or current.owner != game.owner:
            raise GameNotFound(game.id)
        if current.revision != game.revision:
            raise StaleSave(game.id)
        saved = replace(game, revision=game.revision + 1, updated_at=datetime.now(timezone.utc))
        self._games[game.id] = saved
        return saved

    def list_for_owner(self, owner: str) -> list[GameSummary]:
        mine = sorted(
            (g for g in self._games.values() if g.owner == owner),
            key=lambda g: g.updated_at,
            reverse=True,
        )
        return [
            GameSummary(
                id=g.id,
                seats=g.seats,
                phase=g.phase,
                round_label=g.round_label,
                updated_at=g.updated_at,
            )
            for g in mine
        ]

    def delete(self, owner: str, game_id: str) -> None:
        self.get(owner, game_id)
        del self._games[game_id]


def schema_sql() -> str:
    """The idempotent schema that ``bby18 migrate`` applies."""
    return files("bby18.api").joinpath("schema.sql").read_text()


_GAME_COLUMNS = (
    "id, owner, seed, seats, actions, code_version, snapshot, phase, round_label, revision, "
    "updated_at"
)


class PostgresStore:
    """Accounts and games in Postgres (Neon in production).

    Each operation opens a short connection. Serverless instances freeze between requests, so
    a connection held across them would often be dead on the next use; Neon's pooled endpoint
    makes a fresh connection cheap. Prepared statements are off because that pooler runs in
    transaction mode.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    @contextmanager
    def _cursor(self) -> Iterator[psycopg.Cursor[DictRow]]:
        try:
            with psycopg.connect(
                self._database_url, autocommit=True, prepare_threshold=None, row_factory=dict_row
            ) as conn:
                with conn.cursor() as cursor:
                    yield cursor
        except psycopg.Error as exc:
            raise StoreError(f"Database error: {exc}") from exc

    def migrate(self) -> None:
        with self._cursor() as cursor:
            cursor.execute(schema_sql().encode())

    def create_account(self, account_id: str, token_hash: str) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                "insert into accounts (id, token_hash) values (%s, %s)", (account_id, token_hash)
            )

    def account_for_token(self, token_hash: str) -> str:
        with self._cursor() as cursor:
            cursor.execute("select id from accounts where token_hash = %s", (token_hash,))
            row = cursor.fetchone()
        if row is None:
            raise AccountNotFound()
        account_id: str = row["id"]
        return account_id

    def create(self, game: SavedGame) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                f"insert into games ({_GAME_COLUMNS}) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                _to_params(game),
            )

    def get(self, owner: str, game_id: str) -> SavedGame:
        with self._cursor() as cursor:
            cursor.execute(
                f"select {_GAME_COLUMNS} from games where id = %s and owner = %s",
                (game_id, owner),
            )
            row = cursor.fetchone()
        if row is None:
            raise GameNotFound(game_id)
        return _from_row(row)

    def update(self, game: SavedGame) -> SavedGame:
        saved = replace(game, revision=game.revision + 1, updated_at=datetime.now(timezone.utc))
        with self._cursor() as cursor:
            cursor.execute(
                "update games set seed = %s, seats = %s, actions = %s, code_version = %s, "
                "snapshot = %s, phase = %s, round_label = %s, revision = %s, updated_at = %s "
                "where id = %s and owner = %s and revision = %s",
                (*_to_params(saved)[2:], game.id, game.owner, game.revision),
            )
            updated = cursor.rowcount
        if updated == 0:
            # Either the game is gone or its revision moved; tell the two apart.
            self.get(game.owner, game.id)
            raise StaleSave(game.id)
        return saved

    def list_for_owner(self, owner: str) -> list[GameSummary]:
        with self._cursor() as cursor:
            cursor.execute(
                "select id, seats, phase, round_label, updated_at from games "
                "where owner = %s order by updated_at desc",
                (owner,),
            )
            rows = cursor.fetchall()
        return [
            GameSummary(
                id=row["id"],
                seats=_seats_from_json(row["seats"]),
                phase=row["phase"],
                round_label=row["round_label"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def delete(self, owner: str, game_id: str) -> None:
        with self._cursor() as cursor:
            cursor.execute("delete from games where id = %s and owner = %s", (game_id, owner))
            deleted = cursor.rowcount
        if deleted == 0:
            raise GameNotFound(game_id)


def _to_params(game: SavedGame) -> tuple[Any, ...]:
    """Column values in ``_GAME_COLUMNS`` order."""
    return (
        game.id,
        game.owner,
        game.seed,
        Jsonb([{"name": s.name, "bot": s.bot} for s in game.seats]),
        Jsonb(list(game.actions)),
        game.code_version,
        game.snapshot,
        game.phase,
        game.round_label,
        game.revision,
        game.updated_at,
    )


def _seats_from_json(seats: list[Json]) -> tuple[Seat, ...]:
    return tuple(Seat(name=s["name"], bot=s["bot"]) for s in seats)


def _from_row(row: DictRow) -> SavedGame:
    return SavedGame(
        id=row["id"],
        owner=row["owner"],
        seed=row["seed"],
        seats=_seats_from_json(row["seats"]),
        actions=tuple(row["actions"]),
        code_version=row["code_version"],
        snapshot=bytes(row["snapshot"]),
        phase=row["phase"],
        round_label=row["round_label"],
        revision=row["revision"],
        updated_at=row["updated_at"],
    )
