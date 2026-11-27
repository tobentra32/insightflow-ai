
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
):
    dataset = Dataset(
        user_id=user_id,
        department_id=department_id,
        name="Department Transfer Test",
        original_filename="department-test.csv",
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


def create_department_audit_entry(
    db_session,
    *,
    user_id,
    dataset_id,
    action,
    old_value,
    new_value,
):
    entry = AuditLog(
        user_id=user_id,
        entity_type="dataset",
        entity_id=dataset_id,
        action=action,
        field_name="department_id",
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


def test_deleted_dataset_audit_access_uses_final_department(
    client,
    db_session,
):
    """
    A dataset moves from Operations to Shipping and is then deleted.

    Operations employees must not retain access to its audit history.
    Shipping employees and administrators must retain access.
    """

    # ---------------------------------------------------------
    # 1. Create departments
    # ---------------------------------------------------------

    operations = create_department(
        db_session,
        "Operations",
    )

    shipping = create_department(
        db_session,
        "Shipping",
    )

    # ---------------------------------------------------------
    # 2. Create users
    # ---------------------------------------------------------

    owner = create_user(
        db_session,
        "deleted-dataset-owner@example.com",
        department_id=operations.id,
    )

    operations_employee = create_user(
        db_session,
        "deleted-dataset-operations@example.com",
        department_id=operations.id,
    )

    shipping_employee = create_user(
        db_session,
        "deleted-dataset-shipping@example.com",
        department_id=shipping.id,
    )

    admin = create_user(
        db_session,
        "deleted-dataset-admin@example.com",
        role="admin",
    )

    # ---------------------------------------------------------
    # 3. Create dataset
    # ---------------------------------------------------------

    dataset = create_dataset(
        db_session,
        owner.id,
        operations.id,
    )

    dataset_id = dataset.id

    # ---------------------------------------------------------
    # 4. Record department history
    # ---------------------------------------------------------

    # Original creation: Operations.
    create_department_audit_entry(
        db_session,
        user_id=owner.id,
        dataset_id=dataset_id,
        action="created",
        old_value=None,
        new_value=operations.id,
    )

    # Transfer: Operations -> Shipping.
    create_department_audit_entry(
        db_session,
        user_id=owner.id,
        dataset_id=dataset_id,
        action="updated",
        old_value=operations.id,
        new_value=shipping.id,
    )

    # Deletion: the final department was Shipping.
    create_department_audit_entry(
        db_session,
        user_id=owner.id,
        dataset_id=dataset_id,
        action="deleted",
        old_value=shipping.id,
        new_value=None,
    )

    # ---------------------------------------------------------
    # 5. Delete the dataset database record
    # ---------------------------------------------------------

    db_session.delete(dataset)
    db_session.commit()
    db_session.expire_all()

    assert db_session.get(Dataset, dataset_id) is None

    # Confirm the audit history survived deletion.
    audit_entries = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.entity_type == "dataset",
            AuditLog.entity_id == dataset_id,
            AuditLog.field_name == "department_id",
        )
        .order_by(AuditLog.id.asc())
        .all()
    )

    assert len(audit_entries) == 3
    assert audit_entries[0].new_value == operations.id
    assert audit_entries[1].new_value == shipping.id
    assert audit_entries[2].old_value == shipping.id
    assert audit_entries[2].action == "deleted"

    # ---------------------------------------------------------
    # 6. Operations employee must be denied
    # ---------------------------------------------------------

    login_response = login(
        client,
        operations_employee.email,
    )

    assert login_response.status_code == 200

    operations_response = client.get(
        f"/api/datasets/{dataset_id}/audit-logs"
    )

    assert operations_response.status_code == 404

    # ---------------------------------------------------------
    # 7. Shipping employee must be allowed
    # ---------------------------------------------------------

    login_response = login(
        client,
        shipping_employee.email,
    )

    assert login_response.status_code == 200

    shipping_response = client.get(
        f"/api/datasets/{dataset_id}/audit-logs"
    )

    assert shipping_response.status_code == 200

    shipping_body = shipping_response.json()

    assert shipping_body["total"] == 3

    # ---------------------------------------------------------
    # 8. Administrator must be allowed
    # ---------------------------------------------------------

    login_response = login(
        client,
        admin.email,
    )

    assert login_response.status_code == 200

    admin_response = client.get(
        f"/api/datasets/{dataset_id}/audit-logs"
    )

    assert admin_response.status_code == 200

    admin_body = admin_response.json()

    assert admin_body["total"] == 3
