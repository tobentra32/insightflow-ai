
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.security import (
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
    decode_access_token,
    hash_password,
    validate_password,
    verify_password,
)


# --------------------------------------------------
# PASSWORD HASHING TESTS
# --------------------------------------------------

def test_password_is_hashed():
    password = "InsightFlow@2026Secure"

    hashed_password = hash_password(password)

    assert hashed_password != password
    assert hashed_password.startswith("$argon2")


def test_correct_password_is_verified():
    password = "InsightFlow@2026Secure"

    hashed_password = hash_password(password)

    assert verify_password(password, hashed_password) is True


def test_incorrect_password_is_rejected():
    password = "InsightFlow@2026Secure"

    hashed_password = hash_password(password)

    assert verify_password("WrongPassword@2026", hashed_password) is False


def test_same_password_produces_different_hashes():
    password = "InsightFlow@2026Secure"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    # Argon2 uses random salts.
    assert first_hash != second_hash

    # Both hashes should still verify the original password.
    assert verify_password(password, first_hash)
    assert verify_password(password, second_hash)


# --------------------------------------------------
# PASSWORD VALIDATION TESTS
# --------------------------------------------------

def test_password_with_at_least_12_characters_is_valid():
    password = "InsightFlow@2026"

    validate_password(password)


def test_password_shorter_than_12_characters_is_rejected():
    password = "Short123"

    with pytest.raises(ValueError):
        validate_password(password)


def test_password_longer_than_128_characters_is_rejected():
    password = "A" * 129

    with pytest.raises(ValueError):
        validate_password(password)


# --------------------------------------------------
# JWT TOKEN TESTS
# --------------------------------------------------

def test_access_token_is_created():
    user_id = 1

    token, expires_in = create_access_token(user_id)

    assert isinstance(token, str)
    assert len(token) > 0
    assert expires_in > 0


def test_access_token_contains_correct_user_id():
    user_id = 25

    token, _ = create_access_token(user_id)

    payload = decode_access_token(token)

    assert payload["sub"] == str(user_id)


def test_access_token_has_correct_type():
    token, _ = create_access_token(1)

    payload = decode_access_token(token)

    assert payload["type"] == "access"


def test_invalid_token_is_rejected():
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("this-is-not-a-valid-token")


def test_expired_token_is_rejected():
    now = datetime.now(timezone.utc)

    payload = {
        "sub": "1",
        "iat": now - timedelta(minutes=30),
        "exp": now - timedelta(minutes=15),
        "type": "access",
    }

    expired_token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired_token)
