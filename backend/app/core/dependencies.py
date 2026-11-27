from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.core.security import decode_access_token


def get_authenticated_user(
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Authenticate the request without enforcing password-change policy.

    This dependency is intended only for authentication endpoints that a
    user must be able to access before changing a temporary password, such
    as viewing their own authentication status and changing their password.
    """

    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not access_token:
        raise credentials_error

    try:
        payload = decode_access_token(access_token)

        if payload.get("type") != "access":
            raise credentials_error

        user_id = int(payload["sub"])

    except Exception:
        raise credentials_error

    user = db.get(User, user_id)

    if user is None or not user.is_active:
        raise credentials_error

    return user


def get_current_user(
    current_user: User = Depends(get_authenticated_user),
) -> User:
    """Return an authenticated user who has completed password setup.

    Normal application endpoints use this dependency. Accounts created or
    reset by an administrator must change their temporary password before
    they can use those endpoints.
    """

    if current_user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You must change your temporary password before "
                "accessing this resource."
            ),
        )

    return current_user


def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )

    return current_user
