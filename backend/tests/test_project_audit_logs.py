
import uuid

from sqlalchemy import select

from app.core.dependencies import get_current_user
from app.models.audit_log import AuditLog
from app.models.department import Department
from app.models.project import Project
from app.models.user import User


def authenticate(client, user):
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: user


def create_department(db_session):
    department = Department(
        name=f"Audit Department {uuid.uuid4().hex[:8]}"
    )
    db_session.add(department)
    db_session.flush()
    return department


def create_user(db_session, department_id=None, role="employee"):
    unique_id = uuid.uuid4().hex[:12]

    user = User(
        name=f"Audit User {unique_id}",
        email=f"audit_{unique_id}@example.com",
        password_hash="test-password-hash",
        role=role,
        department_id=department_id,
        is_active=True,
        must_change_password=False,
    )

    db_session.add(user)
    db_session.flush()
    return user


def create_project(db_session, department_id, created_by):
    project = Project(
        department_id=department_id,
        created_by=created_by,
        customer_name=f"Audit Customer {uuid.uuid4().hex[:8]}",
        destination="China",
        contract_reference="AUDIT-TEST-001",
        description="Audit history API test",
    )

    db_session.add(project)
    db_session.flush()
    return project


def create_project_through_api(client, department, employee):
    authenticate(client, employee)

    response = client.post(
        "/api/projects",
        json={
            "customer_name": "Audit History Customer",
            "destination": "China",
            "contract_reference": "AUDIT-HISTORY-001",
        },
    )

    assert response.status_code == 201
    return response.json()["id"]


def get_audit_logs(db_session, project_id):
    return db_session.scalars(
        select(AuditLog)
        .where(
            AuditLog.entity_type == "project",
            AuditLog.entity_id == project_id,
        )
        .order_by(AuditLog.id)
    ).all()


def test_employee_can_view_audit_history_in_own_department(
    client,
    db_session,
):
    department = create_department(db_session)
    creator = create_user(db_session, department.id)
    colleague = create_user(db_session, department.id)

    project_id = create_project_through_api(
        client,
        department,
        creator,
    )

    authenticate(client, colleague)

    response = client.get(
        f"/api/projects/{project_id}/audit-logs"
    )

    assert response.status_code == 200

    result = response.json()

    assert result["total"] == 6
    assert len(result["items"]) == 6
    assert result["skip"] == 0
    assert result["limit"] == 50

    first_log = result["items"][0]

    assert first_log["entity_type"] == "project"
    assert first_log["entity_id"] == project_id
    assert first_log["action"] == "created"
    assert first_log["user_id"] == creator.id
    assert first_log["changed_by_name"] == creator.name
    assert first_log["field_name"]
    assert "changed_at" in first_log


def test_employee_cannot_view_audit_history_from_another_department(
    client,
    db_session,
):
    department_a = create_department(db_session)
    department_b = create_department(db_session)

    creator = create_user(db_session, department_b.id)
    employee = create_user(db_session, department_a.id)

    project = create_project(
        db_session,
        department_b.id,
        creator.id,
    )

    authenticate(client, employee)

    response = client.get(
        f"/api/projects/{project.id}/audit-logs"
    )

    assert response.status_code == 404


def test_admin_can_view_audit_history_from_another_department(
    client,
    db_session,
):
    department = create_department(db_session)

    creator = create_user(db_session, department.id)
    admin = create_user(db_session, role="admin")

    project_id = create_project_through_api(
        client,
        department,
        creator,
    )

    authenticate(client, admin)

    response = client.get(
        f"/api/projects/{project_id}/audit-logs"
    )

    assert response.status_code == 200
    assert response.json()["total"] == 6


def test_audit_history_returns_old_and_new_values(
    client,
    db_session,
):
    department = create_department(db_session)
    employee = create_user(db_session, department.id)

    project_id = create_project_through_api(
        client,
        department,
        employee,
    )

    authenticate(client, employee)

    update_response = client.patch(
        f"/api/projects/{project_id}",
        json={"destination": "Japan"},
    )

    assert update_response.status_code == 200

    response = client.get(
        f"/api/projects/{project_id}/audit-logs"
    )

    assert response.status_code == 200

    matching_logs = [
        item
        for item in response.json()["items"]
        if item["field_name"] == "destination"
        and item["action"] == "updated"
    ]

    assert len(matching_logs) == 1
    assert matching_logs[0]["old_value"] == "China"
    assert matching_logs[0]["new_value"] == "Japan"
    assert matching_logs[0]["changed_by_name"] == employee.name


def test_audit_history_pagination(
    client,
    db_session,
):
    department = create_department(db_session)
    employee = create_user(db_session, department.id)

    project_id = create_project_through_api(
        client,
        department,
        employee,
    )

    authenticate(client, employee)

    first_response = client.get(
        f"/api/projects/{project_id}/audit-logs",
        params={"skip": 0, "limit": 2},
    )

    second_response = client.get(
        f"/api/projects/{project_id}/audit-logs",
        params={"skip": 2, "limit": 2},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    first_page = first_response.json()
    second_page = second_response.json()

    assert first_page["total"] == 6
    assert second_page["total"] == 6

    assert len(first_page["items"]) == 2
    assert len(second_page["items"]) == 2

    first_ids = {
        item["id"]
        for item in first_page["items"]
    }

    second_ids = {
        item["id"]
        for item in second_page["items"]
    }

    assert first_ids.isdisjoint(second_ids)


def test_audit_history_rejects_invalid_pagination(
    client,
    db_session,
):
    department = create_department(db_session)
    employee = create_user(db_session, department.id)

    project = create_project(
        db_session,
        department.id,
        employee.id,
    )

    authenticate(client, employee)

    response = client.get(
        f"/api/projects/{project.id}/audit-logs",
        params={"skip": -1},
    )

    assert response.status_code == 422


def test_audit_history_returns_404_for_nonexistent_project(
    client,
    db_session,
):
    department = create_department(db_session)
    employee = create_user(db_session, department.id)

    authenticate(client, employee)

    response = client.get(
        "/api/projects/999999999/audit-logs"
    )

    assert response.status_code == 404


def test_audit_history_returns_empty_list_when_project_has_no_logs(
    client,
    db_session,
):
    department = create_department(db_session)
    employee = create_user(db_session, department.id)

    project = create_project(
        db_session,
        department.id,
        employee.id,
    )

    authenticate(client, employee)

    response = client.get(
        f"/api/projects/{project.id}/audit-logs"
    )

    assert response.status_code == 200

    result = response.json()

    assert result["items"] == []
    assert result["total"] == 0
