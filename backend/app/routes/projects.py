from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.department import Department
from app.models.project import Project
from app.models.user import User
from app.schemas.project import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)
from app.services.audit import record_audit_changes


router = APIRouter(
    prefix="/api/projects",
    tags=["Projects"],
)


def get_accessible_project(
    db: Session,
    project_id: int,
    current_user: User,
) -> Project:
    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    if current_user.role == "admin":
        return project

    if current_user.role != "employee":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account does not have permission to access projects.",
        )

    if (
        current_user.department_id is None
        or project.department_id != current_user.department_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    return project


def require_project_editor(
    project: Project,
    current_user: User,
) -> None:
    if current_user.role == "admin":
        return

    if current_user.role != "employee":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify projects.",
        )

    if project.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Only the project creator or an administrator "
                "can modify this project."
            ),
        )


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    payload: ProjectCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "employee":
        if current_user.department_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Your account must be assigned to a department "
                    "before creating projects."
                ),
            )

        if (
            payload.department_id is not None
            and payload.department_id != current_user.department_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employees cannot assign projects to another department.",
            )

        department_id = current_user.department_id

    elif current_user.role == "admin":
        if payload.department_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Administrators must select a department "
                    "for the project."
                ),
            )

        department_id = payload.department_id

    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account does not have permission to create projects.",
        )

    department = db.get(Department, department_id)

    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found.",
        )

    project = Project(
        department_id=department_id,
        created_by=current_user.id,
        customer_name=payload.customer_name,
        destination=payload.destination,
        contract_reference=payload.contract_reference,
        description=payload.description,
    )

    db.add(project)

    # Obtain the generated project ID without committing yet.
    db.flush()

    initial_values = {
        "department_id": project.department_id,
        "customer_name": project.customer_name,
        "destination": project.destination,
        "contract_reference": project.contract_reference,
        "description": project.description,
        "status": project.status,
    }

    record_audit_changes(
        db,
        user_id=current_user.id,
        entity_type="project",
        entity_id=project.id,
        action="created",
        changes={
            field_name: (None, value)
            for field_name, value in initial_values.items()
        },
    )

    db.commit()
    db.refresh(project)

    return project


@router.get("", response_model=ProjectListResponse)
def list_projects(
    department_id: int | None = Query(default=None, gt=0),
    project_status: str | None = Query(
        default=None,
        alias="status",
        pattern="^(active|on_hold|completed|archived)$",
    ),
    search: str | None = Query(default=None, max_length=200),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "employee":
        if current_user.department_id is None:
            return ProjectListResponse(items=[], total=0)

        if (
            department_id is not None
            and department_id != current_user.department_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot view projects from another department.",
            )

        effective_department_id = current_user.department_id

    elif current_user.role == "admin":
        effective_department_id = department_id

    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account does not have permission to view projects.",
        )

    conditions = []

    if effective_department_id is not None:
        conditions.append(
            Project.department_id == effective_department_id
        )

    if project_status:
        conditions.append(Project.status == project_status)

    search_term = search.strip() if search else ""

    if search_term:
        pattern = f"%{search_term}%"

        conditions.append(
            or_(
                Project.customer_name.ilike(pattern),
                Project.destination.ilike(pattern),
                Project.contract_reference.ilike(pattern),
            )
        )

    total = db.scalar(
        select(func.count(Project.id)).where(*conditions)
    ) or 0

    projects = db.scalars(
        select(Project)
        .where(*conditions)
        .order_by(Project.created_at.desc(), Project.id.desc())
        .offset(skip)
        .limit(limit)
    ).all()

    return ProjectListResponse(
        items=projects,
        total=total,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_accessible_project(db, project_id, current_user)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int,
    payload: ProjectUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = get_accessible_project(db, project_id, current_user)
    require_project_editor(project, current_user)

    updates = payload.model_dump(exclude_unset=True)

    if "department_id" in updates:
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Only administrators can reassign projects "
                    "to another department."
                ),
            )

        department = db.get(
            Department,
            updates["department_id"],
        )

        if department is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found.",
            )

    changes = {}

    for field, new_value in updates.items():
        old_value = getattr(project, field)

        if old_value != new_value:
            changes[field] = (old_value, new_value)
            setattr(project, field, new_value)

    if changes:
        action = (
            "department_reassigned"
            if "department_id" in changes
            else "updated"
        )

        record_audit_changes(
            db,
            user_id=current_user.id,
            entity_type="project",
            entity_id=project.id,
            action=action,
            changes=changes,
        )

        db.commit()
        db.refresh(project)

    return project