
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import require_admin
from app.core.security import hash_password, validate_password
from app.database import get_db
from app.models.department import Department
from app.models.user import User
from app.services.audit import record_audit_changes
from app.schemas.admin import (
    AdminUserCreate,
    AdminUserCreatedResponse,
    AdminUserResponse,
    AdminUserUpdate,
    DepartmentCreate,
    DepartmentResponse,
    PasswordResetResponse,
)


router = APIRouter(
    prefix="/api/admin",
    tags=["Administration"],
)


def generate_temporary_password() -> str:
    password = secrets.token_urlsafe(24)
    validate_password(password)
    return password


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "department_id": user.department_id,
        "department_name": (
            user.department.name if user.department else None
        ),
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "created_at": user.created_at,
    }


def get_user_or_404(db: Session, user_id: int) -> User:
    user = (
        db.query(User)
        .options(joinedload(User.department))
        .filter(User.id == user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    return user


def ensure_department_exists(
    db: Session,
    department_id: int | None,
) -> None:
    if department_id is None:
        return

    department = db.get(Department, department_id)

    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found.",
        )


def ensure_employee_has_department(
    role: str,
    department_id: int | None,
) -> None:
    if role == "employee" and department_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employee accounts must belong to a department.",
        )


def ensure_another_active_admin_exists(
    db: Session,
    target_user: User,
) -> None:
    if target_user.role != "admin" or not target_user.is_active:
        return

    active_admin_count = (
        db.query(User)
        .filter(
            User.role == "admin",
            User.is_active.is_(True),
        )
        .count()
    )

    if active_admin_count <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate or demote the last active administrator.",
        )


@router.post(
    "/departments",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_department(
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    name = payload.name.strip()

    if len(name) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Department name must contain at least 2 characters.",
        )

    existing = (
        db.query(Department)
        .filter(func.lower(Department.name) == name.lower())
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A department with this name already exists.",
        )

    department = Department(name=name)
    db.add(department)

    try:
        db.flush()
        record_audit_changes(
            db,
            user_id=current_admin.id,
            entity_type="department",
            entity_id=department.id,
            action="created",
            changes={
                "name": (None, department.name),
            },
        )
        db.commit()
        db.refresh(department)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A department with this name already exists.",
        )

    return department


@router.get(
    "/departments",
    response_model=list[DepartmentResponse],
)
def list_departments(
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    return (
        db.query(Department)
        .order_by(Department.name.asc())
        .all()
    )


@router.post(
    "/users",
    response_model=AdminUserCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: AdminUserCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    email = str(payload.email).strip().lower()
    name = payload.name.strip()

    if len(name) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name must contain at least 2 characters.",
        )

    existing = (
        db.query(User)
        .filter(func.lower(User.email) == email)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    ensure_department_exists(db, payload.department_id)
    ensure_employee_has_department(
        payload.role,
        payload.department_id,
    )

    temporary_password = generate_temporary_password()

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(temporary_password),
        role=payload.role,
        department_id=payload.department_id,
        is_active=True,
        must_change_password=True,
    )

    db.add(user)

    try:
        db.flush()
        record_audit_changes(
            db,
            user_id=current_admin.id,
            entity_type="user",
            entity_id=user.id,
            action="created",
            changes={
                "name": (None, user.name),
                "email": (None, user.email),
                "role": (None, user.role),
                "department_id": (None, user.department_id),
                "is_active": (None, user.is_active),
                "must_change_password": (
                    None,
                    user.must_change_password,
                ),
            },
        )
        db.commit()
        user = get_user_or_404(db, user.id)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    return {
        "message": "User account created successfully.",
        "user": serialize_user(user),
        "temporary_password": temporary_password,
    }


@router.get(
    "/users",
    response_model=list[AdminUserResponse],
)
def list_users(
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    users = (
        db.query(User)
        .options(joinedload(User.department))
        .order_by(User.created_at.desc())
        .all()
    )

    return [serialize_user(user) for user in users]


@router.get(
    "/users/{user_id}",
    response_model=AdminUserResponse,
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    user = get_user_or_404(db, user_id)
    return serialize_user(user)


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserResponse,
)
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    user = get_user_or_404(db, user_id)
    updates = payload.model_dump(exclude_unset=True)

    if user.id == current_admin.id:
        if updates.get("role") == "employee":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot remove your own administrator role.",
            )

        if updates.get("is_active") is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot deactivate your own account.",
            )

    new_role = updates.get("role", user.role)
    new_department_id = updates.get(
        "department_id",
        user.department_id,
    )
    new_active_status = updates.get("is_active", user.is_active)

    ensure_department_exists(db, new_department_id)
    ensure_employee_has_department(
        new_role,
        new_department_id,
    )

    if (
        user.role == "admin"
        and user.is_active
        and (
            new_role != "admin"
            or new_active_status is False
        )
    ):
        ensure_another_active_admin_exists(db, user)

    if "email" in updates:
        email = str(updates["email"]).strip().lower()

        duplicate = (
            db.query(User)
            .filter(
                func.lower(User.email) == email,
                User.id != user.id,
            )
            .first()
        )

        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        updates["email"] = email

    if "name" in updates:
        updates["name"] = updates["name"].strip()

        if len(updates["name"]) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Name must contain at least 2 characters.",
            )

    changes = {}
    for field, value in updates.items():
        old_value = getattr(user, field)
        if old_value != value:
            changes[field] = (old_value, value)
            setattr(user, field, value)

    try:
        record_audit_changes(
            db,
            user_id=current_admin.id,
            entity_type="user",
            entity_id=user.id,
            action="updated",
            changes=changes,
        )
        db.commit()
        user = get_user_or_404(db, user.id)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The account update conflicts with existing data.",
        )

    return serialize_user(user)


@router.post(
    "/users/{user_id}/reset-password",
    response_model=PasswordResetResponse,
)
def reset_user_password(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    user = get_user_or_404(db, user_id)

    temporary_password = generate_temporary_password()
    old_must_change_password = user.must_change_password

    user.password_hash = hash_password(temporary_password)
    user.must_change_password = True

    record_audit_changes(
        db,
        user_id=current_admin.id,
        entity_type="user",
        entity_id=user.id,
        action="password_reset",
        changes={
            "password_reset": (None, True),
            "must_change_password": (
                old_must_change_password,
                True,
            ),
        },
    )

    db.commit()

    return {
        "message": "Password reset successfully. The user must change it at next login.",
        "temporary_password": temporary_password,
        "must_change_password": True,
    }
