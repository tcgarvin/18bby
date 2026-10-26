# Deployment

`https://18bby.tcgarvin.com` is one Vercel project (`18bby`, team "Tim's projects", functions in
`iad1`) with a Neon Postgres database added through the Vercel Marketplace.

```
browser ──▶ Vercel ──┬─ public/ (the built web/ frontend, served from the CDN)
                     └─ /api/*  FastAPI (bby18.api.main:app) as a Python function ──▶ Neon
                                                                  accounts + games tables
```

## How the pieces fit

- **Accounts.** On its first visit the frontend calls `POST /api/accounts` and gets an account
  id and a random token (`web/src/auth.ts`). The browser keeps the token in localStorage and
  sends it as `Authorization: Bearer <token>`; the database stores only its SHA-256
  (`bby18.api.auth`). The same browser is the same player tomorrow. Clearing site data or
  switching browsers starts a new, empty account, and a token the server no longer recognizes
  is reported rather than silently replaced, so saved games are never hidden by a fresh account.
- **Identity at the API.** `TokenAuthenticator` resolves the bearer token to an account id,
  which owns games. Someone else's game answers 404. `/api/board` and `/api/accounts` need no
  token.
- **Saves.** The API is stateless: each request loads the game from the `games` table, acts,
  and writes it back (`bby18.api.store.PostgresStore`, one short connection per operation on
  Neon's pooled endpoint). A save's durable record is seed + seats + submitted actions; the
  pickled session beside it is a cache keyed to a hash of the engine source
  (`bby18.api.saves`). After a deploy that changes the engine, the first load replays the
  actions. A save whose actions are no longer legal under changed rules answers 409 and cannot
  be resumed. Undo replays the save without its last action.
- **Lost updates.** Each write names the `revision` it read; a second tab on an old position
  gets 409 and is told to reload.

## Configuration

| Where | Name | Value |
|---|---|---|
| Vercel env (runtime) | `BBY18_MODE` | `postgres` (the API refuses to start without a mode) |
| Vercel env (runtime) | `DATABASE_URL` | set by the Neon integration (pooled connection string) |

Local play needs neither: `uv run bby18 serve` sets `BBY18_MODE=local` (games in memory, one
local user; account tokens are issued but not needed).

**Rules.** The API serves one rule set, `DEFAULT_CONFIG` (the Death Star and fleets rules since
2026-10-26; see `docs/DECISIONS.md`). The `BBY18_DEATH_STAR_RULES` switch that served them
experimentally before then has been removed; setting it does nothing.

**Saves from before 2026-10-26.** A save records its seed, seats and actions, not its rules, so
after the deploy that adopts the Death Star rules every older save replays from its seed under
them: the board gains the construction sites and every operating turn a fleet step. Most such
games' recorded moves stop being legal (an operating turn now ends with a fleet step), so they
answer 409 and cannot be resumed, as after the terrain change. Players start a new game.

Build: `vercel.json` sets the FastAPI framework and builds the frontend into `public/`.
`[tool.vercel]` in `pyproject.toml` names the entrypoint as a path from the repository root
(`src.bby18.api.main:app`); Vercel installs the package itself with `uv sync --no-editable`, so
imports inside it use `bby18.…` as usual. The deployed app declares `public/` with
`app.frontend(…, check_dir=False)`: Vercel publishes it to the CDN and leaves it out of the
function, so the directory does not exist at runtime. `.vercelignore` drops `.python-version`
(3.11) because Vercel's build image has only 3.12.

## Database

The schema is `src/bby18/api/schema.sql`, written to be idempotent. The deployed API applies it
on every cold start (under an advisory lock, so concurrent starts take turns), because the
integration stores `DATABASE_URL` as a sensitive variable that cannot be read back. It can also
be applied by hand:

```sh
DATABASE_URL='<the Neon connection string>' uv run bby18 migrate
```

`vercel env pull` writes the project's `DATABASE_URL` to `.env.local` (gitignored) if you need
it locally.

Tests for the Postgres store run only when `BBY18_TEST_DATABASE_URL` points at a throwaway
database (the tests drop and recreate the tables), for example:

```sh
docker run -d --rm --name bby18-pg -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:17
BBY18_TEST_DATABASE_URL=postgresql://postgres:test@localhost:55432/postgres uv run pytest tests/test_store.py
docker stop bby18-pg
```

## Setting it up from scratch

1. Create the Vercel project `18bby` (framework FastAPI) and add Neon from the Marketplace
   (Storage → Neon, Free plan, region Washington D.C., Neon Auth off), connected to the project.
2. Add `BBY18_MODE=postgres` for Production and Preview.
   When installing, set the env prefix to `DATABASE` and leave "create database branch for
   deployment" unchecked, so every deployment shares one database.
3. `vercel deploy --prod`. The schema is applied when the API starts.
4. Add the domain `18bby.tcgarvin.com` to the project, and in Cloudflare (zone `tcgarvin.com`) a
   DNS-only (grey cloud) CNAME `18bby` → `5f408df1ec8d31e2.vercel-dns-017.com` (the target
   Vercel recommended for this project on 2026-09-29).

## Later: Google sign-in

Link a Google identity onto the existing account rather than creating a new one, so a player's
games carry over and other devices can reach them. Candidates: Neon Auth (Better Auth), or a
small OAuth flow of our own that adds a `google_sub` column to `accounts`.
