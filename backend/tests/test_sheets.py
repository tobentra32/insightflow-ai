
import json

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


def create_dataset(db_session, user_id, department_id):
    dataset = Dataset(
        user_id=user_id,
        department_id=department_id,
        name="Filtering Dataset",
        original_filename="filtering.csv",
        file_type="csv",
        storage_path=None,
        file_size=100,
        row_count=5,
        column_count=3,
        status="completed",
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)
    return dataset


def create_sheet(db_session, dataset_id):
    sheet = DatasetSheet(
        dataset_id=dataset_id,
        sheet_name="Containers",
        sheet_index=0,
        row_count=5,
        column_count=3,
    )
    db_session.add(sheet)
    db_session.commit()
    db_session.refresh(sheet)

    columns = [
        DatasetColumn(
            sheet_id=sheet.id,
            column_name="container_number",
            column_index=0,
            data_type="string",
            null_count=0,
            is_unique=True,
        ),
        DatasetColumn(
            sheet_id=sheet.id,
            column_name="supplier",
            column_index=1,
            data_type="string",
            null_count=0,
            is_unique=False,
        ),
        DatasetColumn(
            sheet_id=sheet.id,
            column_name="gross_weight",
            column_index=2,
            data_type="number",
            null_count=0,
            is_unique=False,
        ),
    ]

    records = [
        {
            "container_number": "CMAU1000001",
            "supplier": "ABC Minerals",
            "gross_weight": 25000,
        },
        {
            "container_number": "CMAU1000002",
            "supplier": "ABC Minerals",
            "gross_weight": 27000,
        },
        {
            "container_number": "CMAU1000003",
            "supplier": "XYZ Exports",
            "gross_weight": 30000,
        },
        {
            "container_number": "CMAU1000004",
            "supplier": "XYZ Exports",
            "gross_weight": 22000,
        },
        {
            "container_number": "CMAU1000005",
            "supplier": "ABC Minerals",
            "gross_weight": 28000,
        },
    ]

    db_session.add_all(columns)

    db_session.add_all([
        DatasetRecord(
            sheet_id=sheet.id,
            row_index=index + 2,
            data=record,
        )
        for index, record in enumerate(records)
    ])

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


def setup_sheet(client, db_session, email, department_name):
    department = create_department(
        db_session,
        department_name,
    )

    employee = create_user(
        db_session,
        email,
        "employee",
        department.id,
    )

    dataset = create_dataset(
        db_session,
        employee.id,
        department.id,
    )

    sheet = create_sheet(
        db_session,
        dataset.id,
    )

    assert login(client, email).status_code == 200

    return sheet


def get_records(client, sheet_id, filters=None, **params):
    query_params = dict(params)

    if filters is not None:
        query_params["filters"] = json.dumps(filters)

    return client.get(
        f"/api/sheets/{sheet_id}/records",
        params=query_params,
    )


def test_records_endpoint_returns_all_records(
    client,
    db_session,
):
    sheet = setup_sheet(
        client,
        db_session,
        "records-all@example.com",
        "Operations",
    )

    response = client.get(
        f"/api/sheets/{sheet.id}/records"
    )

    assert response.status_code == 200

    result = response.json()

    assert len(result["data"]) == 5
    assert result["pagination"]["total_records"] == 5
    assert result["pagination"]["total_pages"] == 1


def test_filter_records_by_exact_text(
    client,
    db_session,
):
    sheet = setup_sheet(
        client,
        db_session,
        "records-eq@example.com",
        "Operations",
    )

    response = get_records(
        client,
        sheet.id,
        {"supplier": {"eq": "ABC Minerals"}},
    )

    assert response.status_code == 200

    result = response.json()

    assert result["pagination"]["total_records"] == 3
    assert all(
        row["data"]["supplier"] == "ABC Minerals"
        for row in result["data"]
    )


def test_filter_records_by_contains(
    client,
    db_session,
):
    sheet = setup_sheet(
        client,
        db_session,
        "records-contains@example.com",
        "Operations",
    )

    response = get_records(
        client,
        sheet.id,
        {"container_number": {"contains": "1000003"}},
    )

    assert response.status_code == 200

    result = response.json()

    assert result["pagination"]["total_records"] == 1
    assert result["data"][0]["data"]["container_number"] == "CMAU1000003"


def test_filter_records_by_numeric_greater_than(
    client,
    db_session,
):
    sheet = setup_sheet(
        client,
        db_session,
        "records-gt@example.com",
        "Operations",
    )

    response = get_records(
        client,
        sheet.id,
        {"gross_weight": {"gt": 25000}},
    )

    assert response.status_code == 200

    result = response.json()

    assert result["pagination"]["total_records"] == 3

    assert all(
        row["data"]["gross_weight"] > 25000
        for row in result["data"]
    )


def test_filter_records_with_multiple_columns(
    client,
    db_session,
):
    sheet = setup_sheet(
        client,
        db_session,
        "records-multiple@example.com",
        "Operations",
    )

    response = get_records(
        client,
        sheet.id,
        {
            "supplier": {"eq": "ABC Minerals"},
            "gross_weight": {"gte": 27000},
        },
    )

    assert response.status_code == 200

    result = response.json()

    assert result["pagination"]["total_records"] == 2

    for record in result["data"]:
        assert record["data"]["supplier"] == "ABC Minerals"
        assert record["data"]["gross_weight"] >= 27000


def test_filter_records_with_pagination(
    client,
    db_session,
):
    sheet = setup_sheet(
        client,
        db_session,
        "records-pagination@example.com",
        "Operations",
    )

    response = get_records(
        client,
        sheet.id,
        {"supplier": {"eq": "ABC Minerals"}},
        page=2,
        page_size=2,
    )

    assert response.status_code == 200

    result = response.json()

    assert len(result["data"]) == 1
    assert result["pagination"]["total_records"] == 3
    assert result["pagination"]["page"] == 2
    assert result["pagination"]["page_size"] == 2
    assert result["pagination"]["total_pages"] == 2


def test_invalid_filter_json_is_rejected(
    client,
    db_session,
):
    sheet = setup_sheet(
        client,
        db_session,
        "records-invalid-json@example.com",
        "Operations",
    )

    response = client.get(
        f"/api/sheets/{sheet.id}/records",
        params={"filters": "{invalid json"},
    )

    assert response.status_code == 422


def test_unsupported_filter_operator_is_rejected(
    client,
    db_session,
):
    sheet = setup_sheet(
        client,
        db_session,
        "records-invalid-operator@example.com",
        "Operations",
    )

    response = get_records(
        client,
        sheet.id,
        {"supplier": {"regex": "ABC"}},
    )

    assert response.status_code == 422


def test_nonexistent_column_is_rejected(
    client,
    db_session,
):
    sheet = setup_sheet(
        client,
        db_session,
        "records-invalid-column@example.com",
        "Operations",
    )

    response = get_records(
        client,
        sheet.id,
        {"password": {"eq": "anything"}},
    )

    assert response.status_code == 422


def test_numeric_filter_rejects_invalid_values(
    client,
    db_session,
):
    sheet = setup_sheet(
        client,
        db_session,
        "records-invalid-number@example.com",
        "Operations",
    )

    response = get_records(
        client,
        sheet.id,
        {"gross_weight": {"gt": "heavy"}},
    )

    assert response.status_code == 422


def test_employee_cannot_filter_another_department_sheet(
    client,
    db_session,
):
    operations = create_department(
        db_session,
        "Operations",
    )

    shipping = create_department(
        db_session,
        "Shipping",
    )

    operations_user = create_user(
        db_session,
        "records-operations@example.com",
        "employee",
        operations.id,
    )

    shipping_user = create_user(
        db_session,
        "records-shipping@example.com",
        "employee",
        shipping.id,
    )

    dataset = create_dataset(
        db_session,
        shipping_user.id,
        shipping.id,
    )

    sheet = create_sheet(
        db_session,
        dataset.id,
    )

    assert login(
        client,
        operations_user.email,
    ).status_code == 200

    response = get_records(
        client,
        sheet.id,
        {"supplier": {"eq": "ABC Minerals"}},
    )

    assert response.status_code == 404
