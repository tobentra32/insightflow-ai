
import os
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from pwdlib import PasswordHash


load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY or len(SECRET_KEY) < 32:
    raise RuntimeError(
        "SECRET_KEY is missing or too short. "
        "Generate a secure secret and add it to your backend .env file."
    )

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
)

COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash a password using the recommended Argon2 configuration."""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its stored hash."""
    return password_hasher.verify(password, password_hash)


def validate_password(password: str) -> None:
    """Apply the platform's minimum password requirements."""

    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")

    if len(password) > 128:
        raise ValueError("Password cannot exceed 128 characters.")


def create_access_token(user_id: int) -> tuple[str, int]:
    """Create a short-lived JWT access token."""

    expires_in = ACCESS_TOKEN_EXPIRE_MINUTES

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=expires_in)

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": expires_at,
        "type": "access",
    }

    token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    return token, expires_in


def decode_access_token(token: str) -> dict:
    """Verify and decode an access token."""

    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
        options={
            "require": ["sub", "exp", "iat", "type"],
        },
    )
