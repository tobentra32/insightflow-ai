import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.models import (
    AuditLog,
    Dataset,
    DatasetColumn,
    DatasetRecord,
    DatasetSheet,
    Department,
    User,
)


PASSWORD = "InitialPassword123!"


def create_department(db_session):
    department = Department(
        name=f"Record Audit {uuid.uuid4().hex[:8]}"
    )
    db_session.add(department)
    db_session.commit()
    db_session.refresh(department)
    return department


def create_user(db_session, *, role="employee", department_id=None):
    unique_id = uuid.uuid4().hex[:12]
    user = User(
        name=f"Record User {unique_id}",
        email=f"record_{unique_id}@example.com",
        password_hash=hash_password(PASSWORD),
        role=role,
        department_id=department_id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def create_dataset_with_record(db_session, owner):
    dataset = Dataset(
        user_id=owner.id,
        department_id=owner.department_id,
        name="Record Editing Dataset",
        original_filename="containers.csv",
        file_type="csv",
        storage_path=None,
        file_size=128,
        row_count=1,
        column_count=3,
        status="completed",
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)

    sheet = DatasetSheet(
        dataset_id=dataset.id,
        sheet_name="Containers",
        sheet_index=0,
        row_count=1,
        column_count=3,
    )
    db_session.add(sheet)
    db_session.commit()
    db_session.refresh(sheet)

    db_session.add_all(
        [
            DatasetColumn(
                sheet_id=sheet.id,
                column_name="container_number",
                column_index=0,
                data_type="string",
                is_unique=True,
                null_count=0,
            ),
            DatasetColumn(
                sheet_id=sheet.id,
                column_name="supplier",
                column_index=1,
                data_type="string",
                is_unique=False,
                null_count=0,
            ),
            DatasetColumn(
                sheet_id=sheet.id,
                column_name="gross_weight",
                column_index=2,
                data_type="number",
                is_unique=False,
                null_count=0,
            ),
        ]
    )

    record = DatasetRecord(
        sheet_id=sheet.id,
        row_index=2,
        data={
            "container_number": "CMAU1000001",
            "supplier": "ABC Minerals",
            "gross_weight": 25000,
        },
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)

    return dataset, sheet, record


def login(client: TestClient, user: User):
    return client.post(
        "/api/auth/login",
        json={"email": user.email, "password": PASSWORD},
    )


def update_record(client, sheet_id, record_id, changes):
    return client.patch(
        f"/api/sheets/{sheet_id}/records/{record_id}",
        json={"changes": changes},
    )


def test_uploader_can_edit_record_and_each_changed_cell_is_audited(
    client,
    db_session,
):
    department = create_department(db_session)
    owner = create_user(
        db_session,
        department_id=department.id,
    )
    _, sheet, record = create_dataset_with_record(db_session, owner)

    assert login(client, owner).status_code == 200

    response = update_record(
        client,
        sheet.id,
        record.id,
        {
            "gross_weight": 26500,
            "supplier": "ABC Minerals Ltd",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "container_number": "CMAU1000001",
        "supplier": "ABC Minerals Ltd",
        "gross_weight": 26500,
    }

    logs = db_session.scalars(
        select(AuditLog).where(
            AuditLog.entity_type == "dataset_record",
            AuditLog.entity_id == record.id,
        )
    ).all()

    assert len(logs) == 2
    by_field = {log.field_name: log for log in logs}

    assert by_field["gross_weight"].old_value == 25000
    assert by_field["gross_weight"].new_value == 26500
    assert by_field["supplier"].old_value == "ABC Minerals"
    assert by_field["supplier"].new_value == "ABC Minerals Ltd"
    assert all(log.user_id == owner.id for log in logs)
    assert all(log.record_id == record.id for log in logs)
    assert all(log.action == "updated" for log in logs)


def test_same_department_colleague_can_view_but_cannot_edit_record(
    client,
    db_session,
):
    department = create_department(db_session)
    owner = create_user(db_session, department_id=department.id)
    colleague = create_user(db_session, department_id=department.id)
    _, sheet, record = create_dataset_with_record(db_session, owner)

    assert login(client, owner).status_code == 200
    owner_update = update_record(
        client,
        sheet.id,
        record.id,
        {"gross_weight": 26000},
    )
    assert owner_update.status_code == 200

    assert login(client, colleague).status_code == 200

    edit_response = update_record(
        client,
        sheet.id,
        record.id,
        {"gross_weight": 27000},
    )
    assert edit_response.status_code == 403

    view_response = client.get(
        f"/api/sheets/{sheet.id}/records"
    )
    assert view_response.status_code == 200

    history_response = client.get(
        f"/api/sheets/{sheet.id}/records/{record.id}/audit-logs"
    )
    assert history_response.status_code == 200
    assert history_response.json()["total"] == 1


def test_employee_cannot_edit_record_in_another_department(
    client,
    db_session,
):
    owner_department = create_department(db_session)
    other_department = create_department(db_session)
    owner = create_user(
        db_session,
        department_id=owner_department.id,
    )
    other_employee = create_user(
        db_session,
        department_id=other_department.id,
    )
    _, sheet, record = create_dataset_with_record(db_session, owner)

    assert login(client, other_employee).status_code == 200

    response = update_record(
        client,
        sheet.id,
        record.id,
        {"gross_weight": 27000},
    )

    assert response.status_code == 404


def test_administrator_can_edit_record_across_departments(
    client,
    db_session,
):
    department = create_department(db_session)
    owner = create_user(db_session, department_id=department.id)
    admin = create_user(db_session, role="admin")
    _, sheet, record = create_dataset_with_record(db_session, owner)

    assert login(client, admin).status_code == 200

    response = update_record(
        client,
        sheet.id,
        record.id,
        {"gross_weight": 28000},
    )

    assert response.status_code == 200
    assert response.json()["data"]["gross_weight"] == 28000


def test_unknown_column_is_rejected_without_changing_record(
    client,
    db_session,
):
    department = create_department(db_session)
    owner = create_user(db_session, department_id=department.id)
    _, sheet, record = create_dataset_with_record(db_session, owner)

    assert login(client, owner).status_code == 200

    response = update_record(
        client,
        sheet.id,
        record.id,
        {"unknown_column": "unexpected"},
    )

    assert response.status_code == 422
    db_session.refresh(record)
    assert record.data["gross_weight"] == 25000

    log_count = db_session.scalar(
        select(AuditLog.id).where(
            AuditLog.entity_type == "dataset_record",
            AuditLog.entity_id == record.id,
        ).limit(1)
    )
    assert log_count is None


def test_empty_record_changes_are_rejected(
    client,
    db_session,
):
    department = create_department(db_session)
    owner = create_user(db_session, department_id=department.id)
    _, sheet, record = create_dataset_with_record(db_session, owner)

    assert login(client, owner).status_code == 200

    response = update_record(client, sheet.id, record.id, {})

    assert response.status_code == 422


def test_unchanged_values_do_not_create_audit_entries(
    client,
    db_session,
):
    department = create_department(db_session)
    owner = create_user(db_session, department_id=department.id)
    _, sheet, record = create_dataset_with_record(db_session, owner)

    assert login(client, owner).status_code == 200

    response = update_record(
        client,
        sheet.id,
        record.id,
        {"gross_weight": 25000},
    )

    assert response.status_code == 200

    log_count = db_session.scalar(
        select(AuditLog.id).where(
            AuditLog.entity_type == "dataset_record",
            AuditLog.entity_id == record.id,
        ).limit(1)
    )
    assert log_count is None


def test_record_id_must_belong_to_requested_sheet(
    client,
    db_session,
):
    department = create_department(db_session)
    owner = create_user(db_session, department_id=department.id)
    _, sheet, record = create_dataset_with_record(db_session, owner)

    another_sheet = DatasetSheet(
        dataset_id=record.sheet.dataset_id,
        sheet_name="Other worksheet",
        sheet_index=1,
        row_count=1,
        column_count=3,
    )
    db_session.add(another_sheet)
    db_session.commit()
    db_session.refresh(another_sheet)

    assert login(client, owner).status_code == 200

    response = update_record(
        client,
        another_sheet.id,
        record.id,
        {"gross_weight": 29000},
    )

    assert response.status_code == 404



def test_employee_cannot_view_record_history_in_another_department(
    client,
    db_session,
):
    owner_department = create_department(db_session)
    other_department = create_department(db_session)
    owner = create_user(db_session, department_id=owner_department.id)
    other_employee = create_user(
        db_session,
        department_id=other_department.id,
    )
    _, sheet, record = create_dataset_with_record(db_session, owner)

    assert login(client, other_employee).status_code == 200

    response = client.get(
        f"/api/sheets/{sheet.id}/records/{record.id}/audit-logs"
    )

    assert response.status_code == 404


def test_record_editing_refreshes_null_and_uniqueness_metadata(
    client,
    db_session,
):
    department = create_department(db_session)
    owner = create_user(db_session, department_id=department.id)
    _, sheet, record = create_dataset_with_record(db_session, owner)

    duplicate_record = DatasetRecord(
        sheet_id=sheet.id,
        row_index=3,
        data={
            "container_number": "CMAU1000002",
            "supplier": "XYZ Exports",
            "gross_weight": 27000,
        },
    )
    db_session.add(duplicate_record)
    db_session.commit()

    container_column = db_session.scalar(
        select(DatasetColumn).where(
            DatasetColumn.sheet_id == sheet.id,
            DatasetColumn.column_name == "container_number",
        )
    )
    supplier_column = db_session.scalar(
        select(DatasetColumn).where(
            DatasetColumn.sheet_id == sheet.id,
            DatasetColumn.column_name == "supplier",
        )
    )

    assert container_column.is_unique is True
    assert supplier_column.null_count == 0

    assert login(client, owner).status_code == 200

    duplicate_response = update_record(
        client,
        sheet.id,
        record.id,
        {"container_number": "CMAU1000002"},
    )
    assert duplicate_response.status_code == 200

    db_session.refresh(container_column)
    assert container_column.is_unique is False

    null_response = update_record(
        client,
        sheet.id,
        record.id,
        {"supplier": None},
    )
    assert null_response.status_code == 200

    db_session.refresh(supplier_column)
    assert supplier_column.null_count == 1

    restore_response = update_record(
        client,
        sheet.id,
        record.id,
        {
            "container_number": "CMAU1000001",
            "supplier": "ABC Minerals",
        },
    )
    assert restore_response.status_code == 200

    db_session.refresh(container_column)
    db_session.refresh(supplier_column)
    assert container_column.is_unique is True
    assert supplier_column.null_count == 0



def test_non_finite_cell_values_are_rejected(
    client,
    db_session,
):
    department = create_department(db_session)
    owner = create_user(db_session, department_id=department.id)
    _, sheet, record = create_dataset_with_record(db_session, owner)

    assert login(client, owner).status_code == 200

    response = client.patch(
        f"/api/sheets/{sheet.id}/records/{record.id}",
        content=(
            '{"changes":{"gross_weight":NaN}}'
        ),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422

    db_session.refresh(record)
    assert record.data["gross_weight"] == 25000