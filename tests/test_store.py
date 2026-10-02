"""One contract for every store: MemoryStore always, PostgresStore when a database is given.

Set BBY18_TEST_DATABASE_URL to a throwaway Postgres database to run the Postgres cases; each
test drops and recreates the tables there.
"""

import os
from dataclasses import replace
from datetime import datetime, timezone

import psycopg
import pytest

from bby18.api.store import (
    AccountNotFound,
    GameNotFound,
    MemoryStore,
    PostgresStore,
    SavedGame,
    Seat,
    StaleSave,
    StoreError,
)

TEST_DATABASE_URL = os.environ.get("BBY18_TEST_DATABASE_URL", "")


@pytest.fixture(params=["memory", "postgres"])
def store(request):
    if request.param == "memory":
        store = MemoryStore()
    else:
        if not TEST_DATABASE_URL:
            pytest.skip("BBY18_TEST_DATABASE_URL is not set")
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
            conn.execute("drop table if exists games, accounts")
        store = PostgresStore(TEST_DATABASE_URL)
        store.migrate()
        store.migrate()  # idempotent
    store.create_account("alice", "hash-a")
    store.create_account("bob", "hash-b")
    return store


def _game(**changes):
    fields = dict(
        id="g1",
        owner="alice",
        seed=2**40,
        seats=(Seat("Me", False), Seat("Bot", True)),
        actions=({"type": "buy", "corp": "KDY", "par": 60}, {"type": "pass"}),
        code_version="v1",
        snapshot=b"\x00pickled\xff" * 100,
        phase="stock",
        round_label="SR1",
        updated_at=datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc),
    )
    fields.update(changes)
    return SavedGame(**fields)


def test_accounts(store):
    assert store.account_for_token("hash-a") == "alice"
    with pytest.raises(AccountNotFound):
        store.account_for_token("hash-z")
    with pytest.raises(StoreError):
        store.create_account("carol", "hash-a")


def test_round_trip_and_ownership(store):
    store.create(_game())
    assert store.get("alice", "g1") == _game()
    with pytest.raises(GameNotFound):
        store.get("bob", "g1")
    with pytest.raises(StoreError):
        store.create(_game())


def test_update_bumps_revision_and_refuses_stale_writes(store):
    store.create(_game())
    saved = store.update(_game(actions=(), round_label="OR1.1"))
    assert saved.revision == 1
    loaded = store.get("alice", "g1")
    assert loaded.actions == ()
    assert loaded.round_label == "OR1.1"
    assert loaded.revision == 1
    with pytest.raises(StaleSave):
        store.update(_game())
    with pytest.raises(GameNotFound):
        store.update(_game(id="missing"))
    with pytest.raises(GameNotFound):
        store.update(replace(saved, owner="bob"))


def test_list_is_newest_first_and_per_owner(store):
    store.create(_game(id="old"))
    store.create(_game(id="new", updated_at=datetime(2026, 9, 30, tzinfo=timezone.utc)))
    store.create(_game(id="theirs", owner="bob"))
    summaries = store.list_for_owner("alice")
    assert [g.id for g in summaries] == ["new", "old"]
    assert summaries[0].seats == (Seat("Me", False), Seat("Bot", True))
    assert summaries[0].round_label == "SR1"
    assert store.list_for_owner("carol") == []


def test_delete(store):
    store.create(_game())
    with pytest.raises(GameNotFound):
        store.delete("bob", "g1")
    store.delete("alice", "g1")
    with pytest.raises(GameNotFound):
        store.get("alice", "g1")
