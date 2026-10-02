/**
 * Anonymous accounts. On its first visit a browser asks the server for an account and keeps
 * the returned token in localStorage, so the same browser is the same player (with the same
 * saved games) on the next visit. The token is sent as `Authorization: Bearer <token>`.
 *
 * Losing the token (clearing site data, another browser) means a new, empty account. A Google
 * sign-in linked onto the account can fix that later.
 */

const STORAGE_KEY = "bby18.token";

/** The token for this page load, in case localStorage is unavailable (private mode, blocked). */
let sessionToken: string | null = null;
let pendingAccount: Promise<string> | null = null;

function readStoredToken(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeToken(token: string) {
  try {
    window.localStorage.setItem(STORAGE_KEY, token);
  } catch {
    // Storage is unavailable: the account lasts only as long as this page.
  }
}

async function createAccount(): Promise<string> {
  const response = await fetch("/api/accounts", { method: "POST" });
  if (!response.ok) throw new Error(`Could not create an account: ${response.status} ${response.statusText}`);
  const body = (await response.json()) as { accountId: string; token: string };
  sessionToken = body.token;
  storeToken(body.token);
  return body.token;
}

/** The bearer token for API requests, creating an account on first use. */
export async function accessToken(): Promise<string> {
  const existing = sessionToken ?? readStoredToken();
  if (existing) return existing;
  // Several requests can start before the first account exists; share one creation between them.
  pendingAccount ??= createAccount().finally(() => {
    pendingAccount = null;
  });
  return pendingAccount;
}
