
import io

from app.core.security import hash_password
from app.models import Dataset, Department, User
from app.models.audit_log import AuditLog


def create_department(db_session, name):
    department = Department(name=name)
    db_session.add(department)
    db_session.commit()
    db_session.refresh(department)
    return department


def create_user(
    db_session,
    email,
    role="employee",
    department_id=None,
):
    user = User(
        name=email.split("@")[0],
        email=email,
        password_hash=hash_password("InitialPassword123!"),
        role=role,
        department_id=department_id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def create_dataset(
    db_session,
    user_id,
    department_id,
    name="Test Dataset",
):
    dataset = Dataset(
        user_id=user_id,
        department_id=department_id,
        name=name,
        original_filename="test.csv",
        file_type="csv",
        storage_path=None,
        file_size=100,
        row_count=1,
        column_count=1,
        status="completed",
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)
    return dataset


def create_audit_entry(
    db_session,
    *,
    user_id,
    dataset_id,
    field_name,
    old_value,
    new_value,
    action="created",
):
    entry = AuditLog(
        user_id=user_id,
        entity_type="dataset",
        entity_id=dataset_id,
        action=action,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)
    return entry


def login(client, email):
    return client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": "InitialPassword123!",
        },
    )


def get_dataset_audit_logs(db_session, dataset_id):
    return (
        db_session.query(AuditLog)
        .filter(
            AuditLog.entity_type == "dataset",
            AuditLog.entity_id == dataset_id,
        )
        .order_by(AuditLog.id.asc())
        .all()
    )


def test_upload_creates_dataset_audit_logs(
    client,
    db_session,
    monkeypatch,
    tmp_path,
):
    department = create_department(db_session, "Operations")

    employee = create_user(
        db_session,
        "dataset-audit-upload@example.com",
        department_id=department.id,
    )

    monkeypatch.setattr(
        "app.services.ingestion_service.UPLOAD_DIR",
        tmp_path,
    )

    assert login(client, employee.email).status_code == 200

    response = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "audit-test.csv",
                io.BytesIO(b"name,value\nExample,100\n"),
                "text/csv",
            )
        },
    )

    assert response.status_code == 201

    dataset_id = response.json()["data"]["dataset_id"]

    db_session.expire_all()

    dataset = db_session.get(Dataset, dataset_id)
    assert dataset is not None

    logs = get_dataset_audit_logs(db_session, dataset_id)

    assert len(logs) == 9

    logged_fields = {
        log.field_name: log
        for log in logs
    }

    expected_fields = {
        "name",
        "owner_user_id",
        "department_id",
        "original_filename",
        "file_type",
        "file_size",
        "row_count",
        "column_count",
        "status",
    }

    assert set(logged_fields) == expected_fields

    assert all(log.action == "created" for log in logs)

    assert logged_fields["name"].new_value == "audit-test"
    assert logged_fields["owner_user_id"].new_value == employee.id
    assert logged_fields["department_id"].new_value == department.id
    assert logged_fields["original_filename"].new_value == "audit-test.csv"
    assert logged_fields["file_type"].new_value == "csv"
    assert logged_fields["row_count"].new_value == 1
    assert logged_fields["column_count"].new_value == 2
    assert logged_fields["status"].new_value == "completed"


def test_dataset_rename_creates_audit_log(
    client,
    db_session,
):
    department = create_department(db_session, "Operations")

    owner = create_user(
        db_session,
        "dataset-audit-rename@example.com",
        department_id=department.id,
    )

    dataset = create_dataset(
        db_session,
        owner.id,
        department.id,
        "Original Dataset",
    )

    assert login(client, owner.email).status_code == 200

    response = client.patch(
        f"/api/datasets/{dataset.id}",
        json={"name": "Renamed Dataset"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Dataset"

    logs = get_dataset_audit_logs(db_session, dataset.id)

    assert len(logs) == 1

    log = logs[0]

    assert log.action == "updated"
    assert log.field_name == "name"
    assert log.old_value == "Original Dataset"
    assert log.new_value == "Renamed Dataset"
    assert log.user_id == owner.id


def test_renaming_dataset_to_same_name_creates_no_audit_log(
    client,
    db_session,
):
    department = create_department(db_session, "Operations")

    owner = create_user(
        db_session,
        "dataset-audit-same-name@example.com",
        department_id=department.id,
    )

    dataset = create_dataset(
        db_session,
        owner.id,
        department.id,
        "Unchanged Dataset",
    )

    assert login(client, owner.email).status_code == 200

    response = client.patch(
        f"/api/datasets/{dataset.id}",
        json={"name": "Unchanged Dataset"},
    )

    assert response.status_code == 200

    logs = get_dataset_audit_logs(db_session, dataset.id)

    assert logs == []


def test_dataset_deletion_preserves_audit_history(
    client,
    db_session,
):
    department = create_department(db_session, "Operations")

    owner = create_user(
        db_session,
        "dataset-audit-delete@example.com",
        department_id=department.id,
    )

    dataset = create_dataset(
        db_session,
        owner.id,
        department.id,
        "Dataset To Delete",
    )

    dataset_id = dataset.id

    assert login(client, owner.email).status_code == 200

    response = client.delete(
        f"/api/datasets/{dataset_id}"
    )

    assert response.status_code == 200

    db_session.expire_all()

    assert db_session.get(Dataset, dataset_id) is None

    logs = get_dataset_audit_logs(db_session, dataset_id)

    assert len(logs) == 9

    logged_fields = {
        log.field_name: log
        for log in logs
    }

    assert logged_fields["name"].action == "deleted"
    assert logged_fields["name"].old_value == "Dataset To Delete"
    assert logged_fields["name"].new_value is None

    assert logged_fields["owner_user_id"].old_value == owner.id
    assert logged_fields["department_id"].old_value == department.id

    assert all(log.user_id == owner.id for log in logs)


def test_unauthorized_colleague_cannot_create_dataset_audit_logs(
    client,
    db_session,
):
    department = create_department(db_session, "Operations")

    owner = create_user(
        db_session,
        "dataset-audit-owner@example.com",
        department_id=department.id,
    )

    colleague = create_user(
        db_session,
        "dataset-audit-colleague@example.com",
        department_id=department.id,
    )

    dataset = create_dataset(
        db_session,
        owner.id,
        department.id,
    )

    assert login(client, colleague.email).status_code == 200

    rename_response = client.patch(
        f"/api/datasets/{dataset.id}",
        json={"name": "Unauthorized Name"},
    )

    assert rename_response.status_code == 403

    delete_response = client.delete(
        f"/api/datasets/{dataset.id}"
    )

    assert delete_response.status_code == 403

    logs = get_dataset_audit_logs(db_session, dataset.id)

    assert logs == []

    db_session.expire_all()

    unchanged_dataset = db_session.get(Dataset, dataset.id)

    assert unchanged_dataset is not None
    assert unchanged_dataset.name == "Test Dataset"


# ---------------------------------------------------------------------
# Dataset audit-history API tests
# ---------------------------------------------------------------------


def test_employee_can_view_dataset_audit_history_in_own_department(
    client,
    db_session,
):
    department = create_department(db_session, "Operations")

    owner = create_user(
        db_session,
        "dataset-history-owner@example.com",
        department_id=department.id,
    )

    colleague = create_user(
        db_session,
        "dataset-history-colleague@example.com",
        department_id=department.id,
    )

    dataset = create_dataset(
        db_session,
        owner.id,
        department.id,
        "Operations Report",
    )

    create_audit_entry(
        db_session,
        user_id=owner.id,
        dataset_id=dataset.id,
        field_name="name",
        old_value=None,
        new_value="Operations Report",
    )

    create_audit_entry(
        db_session,
        user_id=owner.id,
        dataset_id=dataset.id,
        field_name="row_count",
        old_value=None,
        new_value=25,
    )

    assert login(client, colleague.email).status_code == 200

    response = client.get(
        f"/api/datasets/{dataset.id}/audit-logs"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert body["skip"] == 0
    assert body["limit"] == 50

    first_item = body["items"][0]

    assert first_item["entity_type"] == "dataset"
    assert first_item["entity_id"] == dataset.id
    assert first_item["user_id"] == owner.id
    assert first_item["changed_by_name"] == owner.name
    assert first_item["action"] == "created"
    assert first_item["field_name"] in {"name", "row_count"}


def test_dataset_audit_history_supports_pagination(
    client,
    db_session,
):
    department = create_department(db_session, "Operations")

    owner = create_user(
        db_session,
        "dataset-history-pagination@example.com",
        department_id=department.id,
    )

    dataset = create_dataset(
        db_session,
        owner.id,
        department.id,
    )

    for index in range(3):
        create_audit_entry(
            db_session,
            user_id=owner.id,
            dataset_id=dataset.id,
            field_name=f"field_{index}",
            old_value=None,
            new_value=f"value_{index}",
        )

    assert login(client, owner.email).status_code == 200

    response = client.get(
        f"/api/datasets/{dataset.id}/audit-logs",
        params={
            "skip": 1,
            "limit": 1,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["total"] == 3
    assert len(body["items"]) == 1
    assert body["skip"] == 1
    assert body["limit"] == 1


def test_employee_cannot_view_another_department_dataset_audit_history(
    client,
    db_session,
):
    operations = create_department(db_session, "Operations")
    shipping = create_department(db_session, "Shipping")

    owner = create_user(
        db_session,
        "dataset-history-cross-owner@example.com",
        department_id=operations.id,
    )

    shipping_employee = create_user(
        db_session,
        "dataset-history-shipping@example.com",
        department_id=shipping.id,
    )

    dataset = create_dataset(
        db_session,
        owner.id,
        operations.id,
    )

    create_audit_entry(
        db_session,
        user_id=owner.id,
        dataset_id=dataset.id,
        field_name="name",
        old_value=None,
        new_value=dataset.name,
    )

    assert login(client, shipping_employee.email).status_code == 200

    response = client.get(
        f"/api/datasets/{dataset.id}/audit-logs"
    )

    assert response.status_code == 404


def test_administrator_can_view_dataset_audit_history_across_departments(
    client,
    db_session,
):
    operations = create_department(db_session, "Operations")

    owner = create_user(
        db_session,
        "dataset-history-admin-owner@example.com",
        department_id=operations.id,
    )

    admin = create_user(
        db_session,
        "dataset-history-admin@example.com",
        role="admin",
    )

    dataset = create_dataset(
        db_session,
        owner.id,
        operations.id,
    )

    create_audit_entry(
        db_session,
        user_id=owner.id,
        dataset_id=dataset.id,
        field_name="name",
        old_value=None,
        new_value=dataset.name,
    )

    assert login(client, admin.email).status_code == 200

    response = client.get(
        f"/api/datasets/{dataset.id}/audit-logs"
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_employee_can_view_deleted_dataset_history_in_original_department(
    client,
    db_session,
):
    department = create_department(db_session, "Operations")

    owner = create_user(
        db_session,
        "dataset-deleted-history-owner@example.com",
        department_id=department.id,
    )

    colleague = create_user(
        db_session,
        "dataset-deleted-history-colleague@example.com",
        department_id=department.id,
    )

    dataset = create_dataset(
        db_session,
        owner.id,
        department.id,
        "Deleted Operations Dataset",
    )

    dataset_id = dataset.id

    assert login(client, owner.email).status_code == 200

    delete_response = client.delete(
        f"/api/datasets/{dataset_id}"
    )

    assert delete_response.status_code == 200

    db_session.expire_all()

    assert db_session.get(Dataset, dataset_id) is None

    assert login(client, colleague.email).status_code == 200

    response = client.get(
        f"/api/datasets/{dataset_id}/audit-logs"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["total"] == 9
    assert len(body["items"]) == 9
    assert all(
        item["entity_type"] == "dataset"
        and item["entity_id"] == dataset_id
        for item in body["items"]
    )


def test_employee_cannot_view_deleted_dataset_history_from_another_department(
    client,
    db_session,
):
    operations = create_department(db_session, "Operations")
    shipping = create_department(db_session, "Shipping")

    owner = create_user(
        db_session,
        "dataset-deleted-cross-owner@example.com",
        department_id=operations.id,
    )

    shipping_employee = create_user(
        db_session,
        "dataset-deleted-cross-shipping@example.com",
        department_id=shipping.id,
    )

    dataset = create_dataset(
        db_session,
        owner.id,
        operations.id,
        "Deleted Operations Dataset",
    )

    dataset_id = dataset.id

    assert login(client, owner.email).status_code == 200

    delete_response = client.delete(
        f"/api/datasets/{dataset_id}"
    )

    assert delete_response.status_code == 200

    db_session.expire_all()

    assert db_session.get(Dataset, dataset_id) is None

    assert login(client, shipping_employee.email).status_code == 200

    response = client.get(
        f"/api/datasets/{dataset_id}/audit-logs"
    )

    assert response.status_code == 404


def test_administrator_can_view_deleted_dataset_audit_history(
    client,
    db_session,
):
    department = create_department(db_session, "Operations")

    owner = create_user(
        db_session,
        "dataset-deleted-admin-owner@example.com",
        department_id=department.id,
    )

    admin = create_user(
        db_session,
        "dataset-deleted-admin@example.com",
        role="admin",
    )

    dataset = create_dataset(
        db_session,
        owner.id,
        department.id,
        "Deleted Dataset For Admin",
    )

    dataset_id = dataset.id

    assert login(client, owner.email).status_code == 200

    delete_response = client.delete(
        f"/api/datasets/{dataset_id}"
    )

    assert delete_response.status_code == 200

    assert login(client, admin.email).status_code == 200

    response = client.get(
        f"/api/datasets/{dataset_id}/audit-logs"
    )

    assert response.status_code == 200
    assert response.json()["total"] == 9


def test_deleted_dataset_without_audit_history_returns_404(
    client,
    db_session,
):
    admin = create_user(
        db_session,
        "dataset-history-missing-admin@example.com",
        role="admin",
    )

    assert login(client, admin.email).status_code == 200

    response = client.get(
        "/api/datasets/999999/audit-logs"
    )

    assert response.status_code == 404


def test_dataset_audit_history_includes_legacy_dataset_logs(
    client,
    db_session,
):
    """Older dataset audit rows use dataset_id, not generic entity fields."""

    department = create_department(db_session, "Operations")
    owner = create_user(
        db_session,
        "dataset-legacy-history@example.com",
        department_id=department.id,
    )
    dataset = create_dataset(
        db_session,
        owner.id,
        department.id,
        "Legacy Dataset",
    )

    legacy_entry = AuditLog(
        dataset_id=dataset.id,
        record_id=None,
        user_id=owner.id,
        field_name="name",
        old_value=None,
        new_value="Legacy Dataset",
    )
    db_session.add(legacy_entry)
    db_session.commit()

    assert login(client, owner.email).status_code == 200

    response = client.get(
        f"/api/datasets/{dataset.id}/audit-logs"
    )

    assert response.status_code == 200
    result = response.json()

    assert result["total"] == 1
    assert len(result["items"]) == 1
    assert result["items"][0]["field_name"] == "name"
    assert result["items"][0]["changed_by_name"] == owner.name
    assert result["items"][0]["entity_type"] is None
    assert result["items"][0]["entity_id"] is None
    assert result["items"][0]["action"] is None
