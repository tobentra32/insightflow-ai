import pytest

from app.models.user import User
from app.core.security import hash_password


@pytest.fixture
def create_user(db_session):
    """Factory for creating test employee accounts."""

    def _create_user(
        email="admin@example.com",
        password="InsightFlow@2026Secure",
        role="admin",
        is_active=True,
        must_change_password=False,
    ):
        user = User(
            name="Test User",
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_active=is_active,
            must_change_password=must_change_password,
        )

        db_session.add(user)
        db_session.flush()

        return user

    return _create_user


def test_admin_can_login(client, create_user):
    create_user()

    response = client.post(
        "/api/auth/login",
        json={
            "email": "admin@example.com",
            "password": "InsightFlow@2026Secure",
        },
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Login successful."
    assert response.json()["user"]["role"] == "admin"

    # Verify that the authentication cookie is HTTP-only.
    set_cookie = response.headers.get("set-cookie", "").lower()

    assert "httponly" in set_cookie
    assert "access_token=" in set_cookie


def test_login_rejects_incorrect_password(client, create_user):
    create_user()

    response = client.post(
        "/api/auth/login",
        json={
            "email": "admin@example.com",
            "password": "WrongPassword@2026",
        },
    )

    assert response.status_code == 401


def test_login_rejects_unknown_email(client):
    response = client.post(
        "/api/auth/login",
        json={
            "email": "unknown@example.com",
            "password": "InsightFlow@2026Secure",
        },
    )

    assert response.status_code == 401


def test_inactive_user_cannot_login(client, create_user):
    create_user(is_active=False)

    response = client.post(
        "/api/auth/login",
        json={
            "email": "admin@example.com",
            "password": "InsightFlow@2026Secure",
        },
    )

    assert response.status_code == 403


def test_authenticated_user_can_access_me(client, create_user):
    create_user()

    login_response = client.post(
        "/api/auth/login",
        json={
            "email": "admin@example.com",
            "password": "InsightFlow@2026Secure",
        },
    )

    assert login_response.status_code == 200

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == "admin@example.com"
    assert response.json()["role"] == "admin"


def test_unauthenticated_user_cannot_access_me(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_logout_clears_authentication_cookie(client, create_user):
    create_user()

    client.post(
        "/api/auth/login",
        json={
            "email": "admin@example.com",
            "password": "InsightFlow@2026Secure",
        },
    )

    logout_response = client.post("/api/auth/logout")

    assert logout_response.status_code == 200

    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_user_can_change_password(client, create_user):
    create_user()

    client.post(
        "/api/auth/login",
        json={
            "email": "admin@example.com",
            "password": "InsightFlow@2026Secure",
        },
    )

    response = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "InsightFlow@2026Secure",
            "new_password": "NewInsightFlow@2027",
        },
    )

    assert response.status_code == 200

    # Verify that the new password works.
    client.post("/api/auth/logout")

    login_response = client.post(
        "/api/auth/login",
        json={
            "email": "admin@example.com",
            "password": "NewInsightFlow@2027",
        },
    )

    assert login_response.status_code == 200



def test_temporary_password_user_is_blocked_from_normal_endpoints(
    client,
    create_user,
):
    create_user(
        email="temporary@example.com",
        password="TemporaryPass@2026",
        role="employee",
        must_change_password=True,
    )

    login_response = client.post(
        "/api/auth/login",
        json={
            "email": "temporary@example.com",
            "password": "TemporaryPass@2026",
        },
    )

    assert login_response.status_code == 200
    assert login_response.json()["user"]["must_change_password"] is True

    # The user may check their own status to determine the required next step.
    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["must_change_password"] is True

    # Normal application endpoints remain unavailable until the password changes.
    protected_response = client.get("/api/projects")
    assert protected_response.status_code == 403
    assert protected_response.json()["detail"] == (
        "You must change your temporary password before accessing this resource."
    )


def test_temporary_password_user_can_change_password_and_then_access_app(
    client,
    create_user,
):
    create_user(
        email="temporary@example.com",
        password="TemporaryPass@2026",
        role="employee",
        must_change_password=True,
    )

    login_response = client.post(
        "/api/auth/login",
        json={
            "email": "temporary@example.com",
            "password": "TemporaryPass@2026",
        },
    )
    assert login_response.status_code == 200

    change_response = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "TemporaryPass@2026",
            "new_password": "NewInsightFlow@2027",
        },
    )

    assert change_response.status_code == 200

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["must_change_password"] is False

    protected_response = client.get("/api/projects")
    assert protected_response.status_code == 200
