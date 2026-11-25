
import io

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.models import (
    Dataset,
    DatasetColumn,
    DatasetRecord,
    DatasetSheet,
    Department,
    User,
)


def create_department(db_session, name):
    department = Department(name=name)
    db_session.add(department)
    db_session.commit()
    db_session.refresh(department)
    return department


def create_user(
    db_session,
    email,
    role,
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


def create_sheet_with_data(db_session, dataset_id):
    sheet = DatasetSheet(
        dataset_id=dataset_id,
        sheet_name="Sheet1",
        sheet_index=0,
        row_count=1,
        column_count=1,
    )
    db_session.add(sheet)
    db_session.commit()
    db_session.refresh(sheet)

    column = DatasetColumn(
        sheet_id=sheet.id,
        column_name="name",
        column_index=0,
        data_type="string",
        null_count=0,
        is_unique=True,
    )

    record = DatasetRecord(
        sheet_id=sheet.id,
        row_index=2,
        data={"name": "Test record"},
    )

    db_session.add_all([column, record])
    db_session.commit()

    return sheet


def login(client: TestClient, email: str):
    return client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": "InitialPassword123!",
        },
    )


def test_employee_can_view_same_department_dataset(
    client,
    db_session,
):
    operations = create_department(db_session, "Operations")
    employee = create_user(
        db_session,
        "operations-user@example.com",
        "employee",
        operations.id,
    )
    dataset = create_dataset(
        db_session,
        employee.id,
        operations.id,
    )

    assert login(client, employee.email).status_code == 200

    response = client.get(f"/api/datasets/{dataset.id}")

    assert response.status_code == 200
    assert response.json()["id"] == dataset.id
    assert response.json()["department_id"] == operations.id


def test_employee_cannot_view_other_department_dataset(
    client,
    db_session,
):
    operations = create_department(db_session, "Operations")
    shipping = create_department(db_session, "Shipping")

    employee = create_user(
        db_session,
        "operations-user2@example.com",
        "employee",
        operations.id,
    )

    other_user = create_user(
        db_session,
        "shipping-user@example.com",
        "employee",
        shipping.id,
    )

    dataset = create_dataset(
        db_session,
        other_user.id,
        shipping.id,
    )

    assert login(client, employee.email).status_code == 200

    response = client.get(f"/api/datasets/{dataset.id}")

    assert response.status_code == 404


def test_employee_dataset_list_excludes_other_departments(
    client,
    db_session,
):
    operations = create_department(db_session, "Operations")
    shipping = create_department(db_session, "Shipping")

    operations_user = create_user(
        db_session,
        "operations-list@example.com",
        "employee",
        operations.id,
    )

    shipping_user = create_user(
        db_session,
        "shipping-list@example.com",
        "employee",
        shipping.id,
    )

    own_dataset = create_dataset(
        db_session,
        operations_user.id,
        operations.id,
        "Operations Data",
    )

    create_dataset(
        db_session,
        shipping_user.id,
        shipping.id,
        "Shipping Data",
    )

    assert login(client, operations_user.email).status_code == 200

    response = client.get("/api/datasets")

    assert response.status_code == 200

    dataset_ids = [
        item["id"]
        for item in response.json()["data"]
    ]

    assert own_dataset.id in dataset_ids
    assert len(dataset_ids) == 1


def test_employee_cannot_access_other_department_sheets(
    client,
    db_session,
):
    operations = create_department(db_session, "Operations")
    shipping = create_department(db_session, "Shipping")

    employee = create_user(
        db_session,
        "operations-sheet@example.com",
        "employee",
        operations.id,
    )

    other_user = create_user(
        db_session,
        "shipping-sheet@example.com",
        "employee",
        shipping.id,
    )

    dataset = create_dataset(
        db_session,
        other_user.id,
        shipping.id,
    )

    sheet = create_sheet_with_data(db_session, dataset.id)

    assert login(client, employee.email).status_code == 200

    columns_response = client.get(
        f"/api/sheets/{sheet.id}/columns"
    )

    records_response = client.get(
        f"/api/sheets/{sheet.id}/records"
    )

    assert columns_response.status_code == 404
    assert records_response.status_code == 404


def test_administrator_can_view_all_departments(
    client,
    db_session,
):
    operations = create_department(db_session, "Operations")
    shipping = create_department(db_session, "Shipping")

    operations_user = create_user(
        db_session,
        "operations-admin-test@example.com",
        "employee",
        operations.id,
    )

    shipping_user = create_user(
        db_session,
        "shipping-admin-test@example.com",
        "employee",
        shipping.id,
    )

    admin = create_user(
        db_session,
        "dataset-admin@example.com",
        "admin",
    )

    operations_dataset = create_dataset(
        db_session,
        operations_user.id,
        operations.id,
    )

    shipping_dataset = create_dataset(
        db_session,
        shipping_user.id,
        shipping.id,
    )

    assert login(client, admin.email).status_code == 200

    response = client.get("/api/datasets")

    assert response.status_code == 200

    dataset_ids = {
        item["id"]
        for item in response.json()["data"]
    }

    assert operations_dataset.id in dataset_ids
    assert shipping_dataset.id in dataset_ids


def test_legacy_unclassified_dataset_is_admin_only(
    client,
    db_session,
):
    operations = create_department(db_session, "Operations")

    employee = create_user(
        db_session,
        "legacy-employee@example.com",
        "employee",
        operations.id,
    )

    admin = create_user(
        db_session,
        "legacy-admin@example.com",
        "admin",
    )

    legacy_dataset = create_dataset(
        db_session,
        employee.id,
        None,
        "Legacy Dataset",
    )

    assert login(client, employee.email).status_code == 200

    employee_response = client.get(
        f"/api/datasets/{legacy_dataset.id}"
    )

    assert employee_response.status_code == 404

    client.post("/api/auth/logout")
    assert login(client, admin.email).status_code == 200

    admin_response = client.get(
        f"/api/datasets/{legacy_dataset.id}"
    )

    assert admin_response.status_code == 200


def test_employee_can_upload_only_to_own_department(
    client,
    db_session,
):
    operations = create_department(db_session, "Operations")
    shipping = create_department(db_session, "Shipping")

    employee = create_user(
        db_session,
        "upload-employee@example.com",
        "employee",
        operations.id,
    )

    assert login(client, employee.email).status_code == 200

    response = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "test.csv",
                io.BytesIO(b"name,value\nExample,100\n"),
                "text/csv",
            )
        },
        data={"department_id": str(shipping.id)},
    )

    assert response.status_code == 403

    db_session.expire_all()

    assert (
        db_session.query(Dataset)
        .filter(Dataset.name == "test")
        .count()
        == 0
    )


def test_employee_upload_is_assigned_to_own_department(
    client,
    db_session,
):
    operations = create_department(db_session, "Operations")

    employee = create_user(
        db_session,
        "upload-own-department@example.com",
        "employee",
        operations.id,
    )

    assert login(client, employee.email).status_code == 200

    response = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "operations.csv",
                io.BytesIO(b"name,value\nExample,100\n"),
                "text/csv",
            )
        },
    )

    assert response.status_code == 201

    dataset_id = response.json()["data"]["dataset_id"]

    db_session.expire_all()

    dataset = db_session.get(Dataset, dataset_id)

    assert dataset.user_id == employee.id
    assert dataset.department_id == operations.id


def test_non_uploader_cannot_rename_dataset(
    client,
    db_session,
):
    operations = create_department(db_session, "Operations")

    owner = create_user(
        db_session,
        "dataset-owner@example.com",
        "employee",
        operations.id,
    )

    colleague = create_user(
        db_session,
        "dataset-colleague@example.com",
        "employee",
        operations.id,
    )

    dataset = create_dataset(
        db_session,
        owner.id,
        operations.id,
    )

    assert login(client, colleague.email).status_code == 200

    response = client.patch(
        f"/api/datasets/{dataset.id}",
        json={"name": "Unauthorized Rename"},
    )

    assert response.status_code == 403


def test_uploader_can_rename_own_dataset(
    client,
    db_session,
):
    operations = create_department(db_session, "Operations")

    owner = create_user(
        db_session,
        "rename-owner@example.com",
        "employee",
        operations.id,
    )

    dataset = create_dataset(
        db_session,
        owner.id,
        operations.id,
    )

    assert login(client, owner.email).status_code == 200

    response = client.patch(
        f"/api/datasets/{dataset.id}",
        json={"name": "Updated Dataset"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Dataset"


def test_non_uploader_cannot_delete_dataset(
    client,
    db_session,
):
    operations = create_department(db_session, "Operations")

    owner = create_user(
        db_session,
        "delete-owner@example.com",
        "employee",
        operations.id,
    )

    colleague = create_user(
        db_session,
        "delete-colleague@example.com",
        "employee",
        operations.id,
    )

    dataset = create_dataset(
        db_session,
        owner.id,
        operations.id,
    )

    assert login(client, colleague.email).status_code == 200

    response = client.delete(
        f"/api/datasets/{dataset.id}"
    )

    assert response.status_code == 403


def test_administrator_can_rename_other_department_dataset(
    client,
    db_session,
):
    shipping = create_department(db_session, "Shipping")

    owner = create_user(
        db_session,
        "admin-rename-owner@example.com",
        "employee",
        shipping.id,
    )

    admin = create_user(
        db_session,
        "admin-rename@example.com",
        "admin",
    )

    dataset = create_dataset(
        db_session,
        owner.id,
        shipping.id,
    )

    assert login(client, admin.email).status_code == 200

    response = client.patch(
        f"/api/datasets/{dataset.id}",
        json={"name": "Administrator Updated"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Administrator Updated"
