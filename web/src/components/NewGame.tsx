import { useState } from "react";
import type { FormEvent } from "react";
import type { NewGameResponse, Seat } from "../api";
import { ApiError, createGame } from "../api";

interface NewGameProps {
  onCreated: (response: NewGameResponse) => void;
  notice: string | null;
}

/** Difficulties offered for bot seats, easiest first. More will be added as they are tuned. */
const DIFFICULTIES = [{ value: "easy", label: "Easy" }];
/** Sent as a bot seat's name; the server replaces it with the character it picks. */
const BOT_PLACEHOLDER = "Random opponent";

function botSeat(): Seat {
  return { name: BOT_PLACEHOLDER, bot: true, difficulty: DIFFICULTIES[0].value };
}

const DEFAULT_SEATS: Seat[] = [{ name: "You", bot: false }, botSeat(), botSeat()];

export function NewGame({ onCreated, notice }: NewGameProps) {
  const [seats, setSeats] = useState<Seat[]>(DEFAULT_SEATS);
  const [seed, setSeed] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const seedValue = seed.trim() === "" ? undefined : Number(seed);
  const seedValid = seedValue === undefined || (Number.isInteger(seedValue) && seedValue >= 0);
  const namesValid = seats.every((s) => s.bot || (s.name.trim().length > 0 && s.name.trim().length <= 40));

  function update(index: number, patch: Partial<Seat>) {
    setSeats((current) => current.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  }

  function addSeat() {
    setSeats((current) => [...current, botSeat()]);
  }

  function setBot(index: number, bot: boolean) {
    update(index, bot ? botSeat() : { name: `Player ${index + 1}`, bot: false, difficulty: undefined });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!seedValid || !namesValid) return;
    setBusy(true);
    setError(null);
    try {
      const trimmed = seats.map((s) => ({ ...s, name: s.name.trim() }));
      onCreated(await createGame(trimmed, seedValue));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `Could not reach the server: ${String(err)}`);
      setBusy(false);
    }
  }

  return (
    <form className="newgame__card" onSubmit={submit}>
        <p className="eyebrow">18BBY · Hyperspace commerce</p>
        <h1>New game</h1>
        <p className="muted">
          Two to four seats at one screen. Bot seats are filled with a random named opponent at the
          difficulty you pick; you learn each opponent's strategy when the game ends.
        </p>
        {notice && <div className="notice">{notice}</div>}

        <ol className="seats">
          {seats.map((seat, i) => (
            <li key={i} className="seat">
              <span className="seat__num">{i + 1}</span>
              {seat.bot ? (
                <span className="seat__bot">
                  Random opponent
                  <select
                    aria-label={`Seat ${i + 1} difficulty`}
                    value={seat.difficulty}
                    onChange={(e) => update(i, { difficulty: e.target.value })}
                  >
                    {DIFFICULTIES.map((d) => (
                      <option key={d.value} value={d.value}>
                        {d.label}
                      </option>
                    ))}
                  </select>
                </span>
              ) : (
                <input
                  aria-label={`Seat ${i + 1} name`}
                  value={seat.name}
                  maxLength={40}
                  onChange={(e) => update(i, { name: e.target.value })}
                />
              )}
              <label className="toggle">
                <input type="checkbox" checked={seat.bot} onChange={(e) => setBot(i, e.target.checked)} />
                <span>Bot</span>
              </label>
              <button
                type="button"
                className="link"
                disabled={seats.length <= 2}
                onClick={() => setSeats((current) => current.filter((_, j) => j !== i))}
              >
                remove
              </button>
            </li>
          ))}
        </ol>
        {seats.length < 4 && (
          <button type="button" className="btn btn--small" onClick={addSeat}>
            Add seat
          </button>
        )}

        <label className="field">
          <span>Seed (optional)</span>
          <input value={seed} inputMode="numeric" placeholder="random" onChange={(e) => setSeed(e.target.value)} />
        </label>
        {!seedValid && <p className="error">Seed must be a whole number.</p>}
        {seats.every((s) => s.bot) && <p className="muted">All seats are bots: the game will play to the end at once.</p>}
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}

        <button type="submit" className="btn btn--primary btn--wide" disabled={busy || !seedValid || !namesValid}>
          {busy ? "Starting…" : "Start game"}
        </button>
    </form>
  );
}
