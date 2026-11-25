
import uuid

import pytest

from app.core.dependencies import get_current_user
from app.models.department import Department
from app.models.project import Project
from app.models.user import User


def authenticate(client, user):
    """Authenticate API requests as a specific test user."""
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: user


def create_department(db_session, name=None):
    department = Department(
        name=name or f"Test Department {uuid.uuid4().hex[:8]}"
    )
    db_session.add(department)
    db_session.flush()
    return department


def create_user(
    db_session,
    department_id=None,
    role="employee",
):
    unique_id = uuid.uuid4().hex[:12]

    user = User(
        name=f"Test User {unique_id}",
        email=f"test_{unique_id}@example.com",
        password_hash="test-password-hash",
        role=role,
        department_id=department_id,
        is_active=True,
        must_change_password=False,
    )

    db_session.add(user)
    db_session.flush()

    return user


def create_project(
    db_session,
    department_id,
    created_by,
    customer_name=None,
):
    project = Project(
        department_id=department_id,
        created_by=created_by,
        customer_name=customer_name or f"Customer {uuid.uuid4().hex[:8]}",
        destination="China",
        contract_reference="TEST-CONTRACT-001",
        description="Automated permission test",
    )

    db_session.add(project)
    db_session.flush()

    return project


# --------------------------------------------------
# PROJECT CREATION
# --------------------------------------------------

def test_employee_creates_project_in_own_department(
    client,
    db_session,
):
    department = create_department(db_session)
    employee = create_user(
        db_session,
        department_id=department.id,
    )

    authenticate(client, employee)

    response = client.post(
        "/api/projects",
        json={
            "customer_name": "ABC Trading",
            "destination": "China",
            "contract_reference": "ABC-001",
        },
    )

    assert response.status_code == 201
    assert response.json()["department_id"] == department.id
    assert response.json()["created_by"] == employee.id


def test_employee_cannot_create_project_in_another_department(
    client,
    db_session,
):
    department_a = create_department(db_session)
    department_b = create_department(db_session)

    employee = create_user(
        db_session,
        department_id=department_a.id,
    )

    authenticate(client, employee)

    response = client.post(
        "/api/projects",
        json={
            "customer_name": "ABC Trading",
            "destination": "China",
            "department_id": department_b.id,
        },
    )

    assert response.status_code == 403


def test_employee_without_department_cannot_create_project(
    client,
    db_session,
):
    employee = create_user(
        db_session,
        department_id=None,
    )

    authenticate(client, employee)

    response = client.post(
        "/api/projects",
        json={
            "customer_name": "ABC Trading",
            "destination": "China",
        },
    )

    assert response.status_code == 403


def test_admin_can_create_project_in_another_department(
    client,
    db_session,
):
    department = create_department(db_session)
    admin = create_user(
        db_session,
        role="admin",
    )

    authenticate(client, admin)

    response = client.post(
        "/api/projects",
        json={
            "customer_name": "ABC Trading",
            "destination": "China",
            "department_id": department.id,
        },
    )

    assert response.status_code == 201
    assert response.json()["department_id"] == department.id


def test_admin_must_select_department_when_creating_project(
    client,
    db_session,
):
    admin = create_user(
        db_session,
        role="admin",
    )

    authenticate(client, admin)

    response = client.post(
        "/api/projects",
        json={
            "customer_name": "ABC Trading",
            "destination": "China",
        },
    )

    assert response.status_code == 422


# --------------------------------------------------
# PROJECT VISIBILITY
# --------------------------------------------------

def test_employee_can_view_project_in_own_department(
    client,
    db_session,
):
    department = create_department(db_session)

    creator = create_user(
        db_session,
        department_id=department.id,
    )

    colleague = create_user(
        db_session,
        department_id=department.id,
    )

    project = create_project(
        db_session,
        department.id,
        creator.id,
    )

    authenticate(client, colleague)

    response = client.get(
        f"/api/projects/{project.id}"
    )

    assert response.status_code == 200
    assert response.json()["id"] == project.id


def test_employee_cannot_view_another_department_project(
    client,
    db_session,
):
    department_a = create_department(db_session)
    department_b = create_department(db_session)

    employee = create_user(
        db_session,
        department_id=department_a.id,
    )

    creator = create_user(
        db_session,
        department_id=department_b.id,
    )

    project = create_project(
        db_session,
        department_b.id,
        creator.id,
    )

    authenticate(client, employee)

    response = client.get(
        f"/api/projects/{project.id}"
    )

    assert response.status_code == 404


def test_employee_project_list_only_contains_own_department(
    client,
    db_session,
):
    department_a = create_department(db_session)
    department_b = create_department(db_session)

    employee = create_user(
        db_session,
        department_id=department_a.id,
    )

    creator_a = create_user(
        db_session,
        department_id=department_a.id,
    )

    creator_b = create_user(
        db_session,
        department_id=department_b.id,
    )

    project_a = create_project(
        db_session,
        department_a.id,
        creator_a.id,
        "Customer A",
    )

    create_project(
        db_session,
        department_b.id,
        creator_b.id,
        "Customer B",
    )

    authenticate(client, employee)

    response = client.get("/api/projects")

    assert response.status_code == 200

    result = response.json()

    assert result["total"] == 1
    assert len(result["items"]) == 1
    assert result["items"][0]["id"] == project_a.id


def test_employee_cannot_filter_projects_by_another_department(
    client,
    db_session,
):
    department_a = create_department(db_session)
    department_b = create_department(db_session)

    employee = create_user(
        db_session,
        department_id=department_a.id,
    )

    authenticate(client, employee)

    response = client.get(
        f"/api/projects?department_id={department_b.id}"
    )

    assert response.status_code == 403


# --------------------------------------------------
# PROJECT MODIFICATION
# --------------------------------------------------

def test_project_creator_can_update_project(
    client,
    db_session,
):
    department = create_department(db_session)

    creator = create_user(
        db_session,
        department_id=department.id,
    )

    project = create_project(
        db_session,
        department.id,
        creator.id,
    )

    authenticate(client, creator)

    response = client.patch(
        f"/api/projects/{project.id}",
        json={
            "destination": "Japan",
        },
    )

    assert response.status_code == 200
    assert response.json()["destination"] == "Japan"


def test_colleague_cannot_update_another_employees_project(
    client,
    db_session,
):
    department = create_department(db_session)

    creator = create_user(
        db_session,
        department_id=department.id,
    )

    colleague = create_user(
        db_session,
        department_id=department.id,
    )

    project = create_project(
        db_session,
        department.id,
        creator.id,
    )

    authenticate(client, colleague)

    response = client.patch(
        f"/api/projects/{project.id}",
        json={
            "destination": "Japan",
        },
    )

    assert response.status_code == 403


def test_admin_can_update_another_employees_project(
    client,
    db_session,
):
    department = create_department(db_session)

    creator = create_user(
        db_session,
        department_id=department.id,
    )

    admin = create_user(
        db_session,
        role="admin",
    )

    project = create_project(
        db_session,
        department.id,
        creator.id,
    )

    authenticate(client, admin)

    response = client.patch(
        f"/api/projects/{project.id}",
        json={
            "destination": "Japan",
        },
    )

    assert response.status_code == 200
    assert response.json()["destination"] == "Japan"


def test_employee_cannot_reassign_project_department(
    client,
    db_session,
):
    department_a = create_department(db_session)
    department_b = create_department(db_session)

    employee = create_user(
        db_session,
        department_id=department_a.id,
    )

    project = create_project(
        db_session,
        department_a.id,
        employee.id,
    )

    authenticate(client, employee)

    response = client.patch(
        f"/api/projects/{project.id}",
        json={
            "department_id": department_b.id,
        },
    )

    assert response.status_code == 403

    db_session.refresh(project)
    assert project.department_id == department_a.id


def test_admin_can_reassign_project_department(
    client,
    db_session,
):
    department_a = create_department(db_session)
    department_b = create_department(db_session)

    creator = create_user(
        db_session,
        department_id=department_a.id,
    )

    admin = create_user(
        db_session,
        role="admin",
    )

    project = create_project(
        db_session,
        department_a.id,
        creator.id,
    )

    authenticate(client, admin)

    response = client.patch(
        f"/api/projects/{project.id}",
        json={
            "department_id": department_b.id,
        },
    )

    assert response.status_code == 200
    assert response.json()["department_id"] == department_b.id


# --------------------------------------------------
# VALIDATION
# --------------------------------------------------

def test_project_rejects_empty_customer_name(
    client,
    db_session,
):
    department = create_department(db_session)

    employee = create_user(
        db_session,
        department_id=department.id,
    )

    authenticate(client, employee)

    response = client.post(
        "/api/projects",
        json={
            "customer_name": "   ",
            "destination": "China",
        },
    )

    assert response.status_code == 422


def test_project_rejects_empty_update(
    client,
    db_session,
):
    department = create_department(db_session)

    employee = create_user(
        db_session,
        department_id=department.id,
    )

    project = create_project(
        db_session,
        department.id,
        employee.id,
    )

    authenticate(client, employee)

    response = client.patch(
        f"/api/projects/{project.id}",
        json={},
    )

    assert response.status_code == 422


def test_project_rejects_invalid_status(
    client,
    db_session,
):
    department = create_department(db_session)

    employee = create_user(
        db_session,
        department_id=department.id,
    )

    project = create_project(
        db_session,
        department.id,
        employee.id,
    )

    authenticate(client, employee)

    response = client.patch(
        f"/api/projects/{project.id}",
        json={
            "status": "cancelled",
        },
    )

    assert response.status_code == 422
