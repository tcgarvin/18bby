"""Who is calling: the identity boundary of the API.

Accounts are anonymous. On its first visit a browser asks for one (``POST /api/accounts``) and
gets back a random token, which it keeps in localStorage and sends on every request as
``Authorization: Bearer <token>``. The server stores only the token's SHA-256, and
``TokenAuthenticator`` looks the caller up by it. Linking a Google sign-in onto an existing
account can come later without changing account ids.

``FixedUserAuthenticator`` stands in for local play, where everyone is one local user.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from typing import Protocol

from bby18.api.store import AccountNotFound, AccountStore


class AuthError(Exception):
    """The caller did not present a valid token."""


class Authenticator(Protocol):
    def user_id(self, authorization: str) -> str:
        """Return the caller's user id from the Authorization header value, or raise AuthError."""
        ...


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class NewAccount:
    account_id: str
    token: str
    """Shown to the browser once; the store keeps only its hash."""


def create_account(accounts: AccountStore) -> NewAccount:
    account = NewAccount(account_id=str(uuid.uuid4()), token=secrets.token_urlsafe(32))
    accounts.create_account(account.account_id, hash_token(account.token))
    return account


class TokenAuthenticator:
    def __init__(self, accounts: AccountStore) -> None:
        self._accounts = accounts

    def user_id(self, authorization: str) -> str:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise AuthError("Expected an Authorization: Bearer <token> header")
        try:
            return self._accounts.account_for_token(hash_token(token))
        except AccountNotFound as exc:
            raise AuthError("This browser's account token is not recognized") from exc


class FixedUserAuthenticator:
    """Treats every caller as one user. For local play and tests only."""

    def __init__(self, user: str) -> None:
        self._user = user

    def user_id(self, authorization: str) -> str:
        return self._user
