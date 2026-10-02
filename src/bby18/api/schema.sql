-- Schema for the deployed store (bby18.api.store.PostgresStore). Applied by `bby18 migrate`;
-- every statement is idempotent, so running it again is safe. The API also applies it when it
-- starts, so several instances can run it at once: the advisory lock (held to the end of this
-- transaction) makes them take turns instead of racing on "create table if not exists".
select pg_advisory_xact_lock(1818);

-- Anonymous accounts. The browser holds the token; only its SHA-256 is stored here, so a copy
-- of this table cannot be used to act as anyone.
create table if not exists accounts (
    id text primary key,
    token_hash text not null unique,
    created_at timestamptz not null default now()
);

-- One row per saved game. seed, seats and actions are the durable record: replaying the
-- submitted actions from the seed rebuilds the game. snapshot is a cached, zlib-compressed
-- pickle of the session, valid only while code_version matches the running engine. revision
-- guards against lost updates: every write names the revision it read and bumps it.
create table if not exists games (
    id text primary key,
    owner text not null references accounts (id) on delete cascade,
    seed bigint not null,
    seats jsonb not null,
    actions jsonb not null,
    code_version text not null,
    snapshot bytea not null,
    phase text not null,
    round_label text not null,
    revision integer not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists games_owner_updated_at on games (owner, updated_at desc);
