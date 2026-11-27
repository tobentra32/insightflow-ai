
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


def create_sorting_test_data(db_session):
    department = Department(name="Sorting Operations")
    db_session.add(department)
    db_session.commit()
    db_session.refresh(department)

    user = User(
        name="Sorting Employee",
        email="sorting-employee@example.com",
        password_hash=hash_password("InitialPassword123!"),
        role="employee",
        department_id=department.id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    dataset = Dataset(
        user_id=user.id,
        department_id=department.id,
        name="Sorting Dataset",
        original_filename="sorting.csv",
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

    sheet = DatasetSheet(
        dataset_id=dataset.id,
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

    return user, sheet


def login(client: TestClient, email: str):
    return client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": "InitialPassword123!",
        },
    )


def test_sort_numeric_column_ascending(client, db_session):
    user, sheet = create_sorting_test_data(db_session)

    assert login(client, user.email).status_code == 200

    response = client.get(
        f"/api/sheets/{sheet.id}/records",
        params={
            "sort_by": "gross_weight",
            "sort_order": "asc",
        },
    )

    assert response.status_code == 200

    weights = [
        record["data"]["gross_weight"]
        for record in response.json()["data"]
    ]

    assert weights == [22000, 25000, 27000, 28000, 30000]


def test_sort_numeric_column_descending(client, db_session):
    user, sheet = create_sorting_test_data(db_session)

    assert login(client, user.email).status_code == 200

    response = client.get(
        f"/api/sheets/{sheet.id}/records",
        params={
            "sort_by": "gross_weight",
            "sort_order": "desc",
        },
    )

    assert response.status_code == 200

    weights = [
        record["data"]["gross_weight"]
        for record in response.json()["data"]
    ]

    assert weights == [30000, 28000, 27000, 25000, 22000]


def test_sort_text_column_ascending(client, db_session):
    user, sheet = create_sorting_test_data(db_session)

    assert login(client, user.email).status_code == 200

    response = client.get(
        f"/api/sheets/{sheet.id}/records",
        params={
            "sort_by": "supplier",
            "sort_order": "asc",
        },
    )

    assert response.status_code == 200

    suppliers = [
        record["data"]["supplier"]
        for record in response.json()["data"]
    ]

    assert suppliers == [
        "ABC Minerals",
        "ABC Minerals",
        "ABC Minerals",
        "XYZ Exports",
        "XYZ Exports",
    ]


def test_sorting_works_with_filtering_and_pagination(
    client,
    db_session,
):
    user, sheet = create_sorting_test_data(db_session)

    assert login(client, user.email).status_code == 200

    response = client.get(
        f"/api/sheets/{sheet.id}/records",
        params={
            "filters": '{"supplier":{"eq":"ABC Minerals"}}',
            "sort_by": "gross_weight",
            "sort_order": "desc",
            "page": 2,
            "page_size": 2,
        },
    )

    assert response.status_code == 200

    result = response.json()

    assert result["pagination"]["total_records"] == 3
    assert result["pagination"]["total_pages"] == 2
    assert result["pagination"]["page"] == 2

    assert [
        record["data"]["gross_weight"]
        for record in result["data"]
    ] == [25000]


def test_sorting_by_nonexistent_column_is_rejected(
    client,
    db_session,
):
    user, sheet = create_sorting_test_data(db_session)

    assert login(client, user.email).status_code == 200

    response = client.get(
        f"/api/sheets/{sheet.id}/records",
        params={
            "sort_by": "password",
            "sort_order": "asc",
        },
    )

    assert response.status_code == 422


def test_invalid_sort_order_is_rejected(client, db_session):
    user, sheet = create_sorting_test_data(db_session)

    assert login(client, user.email).status_code == 200

    response = client.get(
        f"/api/sheets/{sheet.id}/records",
        params={
            "sort_by": "gross_weight",
            "sort_order": "sideways",
        },
    )

    assert response.status_code == 422


def test_default_order_remains_row_index_order(
    client,
    db_session,
):
    user, sheet = create_sorting_test_data(db_session)

    assert login(client, user.email).status_code == 200

    response = client.get(
        f"/api/sheets/{sheet.id}/records"
    )

    assert response.status_code == 200

    containers = [
        record["data"]["container_number"]
        for record in response.json()["data"]
    ]

    assert containers == [
        "CMAU1000001",
        "CMAU1000002",
        "CMAU1000003",
        "CMAU1000004",
        "CMAU1000005",
    ]
