
import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient

from app.core.security import hash_password, verify_password
from app.models.audit_log import AuditLog
from app.models.department import Department
from app.models.user import User


def create_user(
    db_session,
    email,
    role,
    department_id=None,
    is_active=True,
):
    user = User(
        name="Test User",
        email=email,
        password_hash=hash_password("InitialPassword123!"),
        role=role,
        department_id=department_id,
        is_active=is_active,
        must_change_password=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def login(client: TestClient, email: str):
    return client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": "InitialPassword123!",
        },
    )


@pytest.fixture
def department(db_session):
    department = Department(name="Operations")
    db_session.add(department)
    db_session.commit()
    db_session.refresh(department)
    return department


@pytest.fixture
def admin_user(db_session):
    return create_user(
        db_session,
        "admin-test@example.com",
        "admin",
    )


@pytest.fixture
def employee_user(db_session, department):
    return create_user(
        db_session,
        "employee-test@example.com",
        "employee",
        department.id,
    )


def test_admin_can_create_department(client, admin_user, db_session):
    login_response = login(client, admin_user.email)
    assert login_response.status_code == 200

    response = client.post(
        "/api/admin/departments",
        json={"name": "Documentation"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Documentation"

    department_id = response.json()["id"]
    audit_logs = db_session.scalars(
        select(AuditLog).where(
            AuditLog.entity_type == "department",
            AuditLog.entity_id == department_id,
        )
    ).all()

    assert len(audit_logs) == 1
    assert audit_logs[0].action == "created"
    assert audit_logs[0].field_name == "name"
    assert audit_logs[0].old_value is None
    assert audit_logs[0].new_value == "Documentation"
    assert audit_logs[0].user_id == admin_user.id


def test_admin_can_create_employee(
    client,
    admin_user,
    department,
    db_session,
):
    login_response = login(client, admin_user.email)
    assert login_response.status_code == 200

    response = client.post(
        "/api/admin/users",
        json={
            "name": "New Employee",
            "email": "new-employee@example.com",
            "role": "employee",
            "department_id": department.id,
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["user"]["email"] == "new-employee@example.com"
    assert data["user"]["role"] == "employee"
    assert data["user"]["department_id"] == department.id
    assert data["user"]["must_change_password"] is True
    assert len(data["temporary_password"]) >= 12

    audit_logs = db_session.scalars(
        select(AuditLog).where(
            AuditLog.entity_type == "user",
            AuditLog.entity_id == data["user"]["id"],
        )
    ).all()

    assert {log.field_name for log in audit_logs} == {
        "name",
        "email",
        "role",
        "department_id",
        "is_active",
        "must_change_password",
    }
    assert all(log.action == "created" for log in audit_logs)
    assert all(log.user_id == admin_user.id for log in audit_logs)
    assert data["temporary_password"] not in {
        str(log.old_value) for log in audit_logs
    } | {str(log.new_value) for log in audit_logs}


def test_admin_cannot_create_employee_without_department(
    client,
    admin_user,
):
    login(client, admin_user.email)

    response = client.post(
        "/api/admin/users",
        json={
            "name": "Employee Without Department",
            "email": "no-department@example.com",
            "role": "employee",
        },
    )

    assert response.status_code == 400


def test_duplicate_email_is_rejected(
    client,
    admin_user,
    department,
):
    login(client, admin_user.email)

    payload = {
        "name": "New Employee",
        "email": "duplicate@example.com",
        "role": "employee",
        "department_id": department.id,
    }

    first_response = client.post(
        "/api/admin/users",
        json=payload,
    )

    second_response = client.post(
        "/api/admin/users",
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_employee_cannot_access_admin_endpoints(
    client,
    employee_user,
):
    login(client, employee_user.email)

    response = client.get("/api/admin/users")

    assert response.status_code == 403


def test_admin_can_list_users(client, admin_user):
    login(client, admin_user.email)

    response = client.get("/api/admin/users")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_admin_cannot_deactivate_own_account(
    client,
    admin_user,
):
    login(client, admin_user.email)

    response = client.patch(
        f"/api/admin/users/{admin_user.id}",
        json={"is_active": False},
    )

    assert response.status_code == 400


def test_last_active_admin_cannot_be_demoted(
    client,
    admin_user,
):
    login(client, admin_user.email)

    response = client.patch(
        f"/api/admin/users/{admin_user.id}",
        json={"role": "employee"},
    )

    assert response.status_code == 400


def test_admin_can_reset_employee_password(
    client,
    db_session,
    admin_user,
    employee_user,
):
    login(client, admin_user.email)

    response = client.post(
        f"/api/admin/users/{employee_user.id}/reset-password"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["must_change_password"] is True
    assert len(data["temporary_password"]) >= 12

    db_session.refresh(employee_user)

    assert employee_user.must_change_password is True
    assert verify_password(
        data["temporary_password"],
        employee_user.password_hash,
    )

    reset_logs = db_session.scalars(
        select(AuditLog).where(
            AuditLog.entity_type == "user",
            AuditLog.entity_id == employee_user.id,
            AuditLog.action == "password_reset",
        )
    ).all()

    assert len(reset_logs) == 2

    reset_fields = {log.field_name for log in reset_logs}

    assert reset_fields == {
        "password_reset",
        "must_change_password",
    }

    password_reset_log = next(
        log for log in reset_logs
        if log.field_name == "password_reset"
    )

    assert password_reset_log.new_value is True

    assert all(
        data["temporary_password"] not in str(log.old_value)
        and data["temporary_password"] not in str(log.new_value)
        for log in reset_logs
    )


def test_admin_can_audit_user_profile_updates(
    client,
    db_session,
    admin_user,
    employee_user,
):
    login(client, admin_user.email)

    response = client.patch(
        f"/api/admin/users/{employee_user.id}",
        json={"name": "Updated Employee Name"},
    )

    assert response.status_code == 200

    name_logs = db_session.scalars(
        select(AuditLog).where(
            AuditLog.entity_type == "user",
            AuditLog.entity_id == employee_user.id,
            AuditLog.field_name == "name",
        )
    ).all()

    assert len(name_logs) == 1
    assert name_logs[0].action == "updated"
    assert name_logs[0].old_value == "Test User"
    assert name_logs[0].new_value == "Updated Employee Name"
    assert name_logs[0].user_id == admin_user.id


def test_unauthenticated_user_cannot_access_admin_endpoints(client):
    response = client.get("/api/admin/users")

    assert response.status_code == 401
