import pytest

from bby18.api.auth import AuthError, TokenAuthenticator, create_account, hash_token
from bby18.api.store import MemoryStore


def test_new_account_token_identifies_it():
    store = MemoryStore()
    account = create_account(store)
    auth = TokenAuthenticator(store)
    assert auth.user_id(f"Bearer {account.token}") == account.account_id
    assert auth.user_id(f"bearer {account.token}") == account.account_id


def test_only_the_token_hash_is_stored():
    store = MemoryStore()
    account = create_account(store)
    assert store.account_for_token(hash_token(account.token)) == account.account_id
    assert account.token not in repr(vars(store))


def test_accounts_get_distinct_ids_and_tokens():
    store = MemoryStore()
    first, second = create_account(store), create_account(store)
    assert first.account_id != second.account_id
    assert first.token != second.token
    assert len(first.token) >= 40


@pytest.mark.parametrize(
    "header", ["", "Bearer", "Bearer ", "Basic abc", "Bearer not-a-real-token", "token-alone"]
)
def test_bad_headers_are_refused(header):
    store = MemoryStore()
    create_account(store)
    with pytest.raises(AuthError):
        TokenAuthenticator(store).user_id(header)
