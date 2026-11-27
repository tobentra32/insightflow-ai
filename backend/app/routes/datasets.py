
from pathlib import Path
import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.permissions import (
    get_accessible_dataset,
    require_dataset_editor,
)
from app.database import get_db
from app.models import Dataset, DatasetSheet, User
from app.models.audit_log import AuditLog
from app.models.department import Department
from app.schemas.dataset import (
    DatasetAuditLogListResponse,
    DatasetAuditLogResponse,
    DatasetListResponse,
    DatasetDetailResponse,
    DatasetSheetResponse,
    DatasetUpdateRequest,
)
from app.services.audit import record_audit_changes
from app.services.ingestion_service import ingest_dataset


router = APIRouter(
    prefix="/api/datasets",
    tags=["Datasets"],
)

MAX_FILE_SIZE = 50 * 1024 * 1024
UPLOAD_DIR = (
    Path(__file__).resolve().parents[2]
    / "storage"
    / "uploads"
)

logger = logging.getLogger(__name__)


def _department_value_matches(
    value: object,
    department_id: int,
) -> bool:
    """Compare a stored audit value with a department ID safely."""

    if value is None:
        return False

    try:
        return int(str(value)) == department_id
    except (TypeError, ValueError):
        return False


@router.post("/upload", status_code=status.HTTP_201_CREATED)
def upload_dataset(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    department_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a dataset into the authenticated user's department."""

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="A filename is required.",
        )

    extension = Path(file.filename).suffix.lower()

    allowed_extensions = {".xlsx", ".xlsm", ".xls", ".csv"}

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format.",
        )

    if current_user.role == "employee":
        if current_user.department_id is None:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Your account must be assigned to a department "
                    "before uploading datasets."
                ),
            )

        if (
            department_id is not None
            and department_id != current_user.department_id
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "You can only upload datasets into your own department."
                ),
            )

        target_department_id = current_user.department_id

    elif current_user.role == "admin":
        target_department_id = department_id

    else:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to upload datasets.",
        )

    if target_department_id is not None:
        department = db.get(Department, target_department_id)

        if department is None:
            raise HTTPException(
                status_code=404,
                detail="Department not found.",
            )

    file_bytes = file.file.read(MAX_FILE_SIZE + 1)

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty.",
        )

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File size exceeds the 50 MB limit.",
        )

    file.file.seek(0)

    dataset_name = (
        name.strip()
        if name and name.strip()
        else Path(file.filename).stem
    )

    if not dataset_name:
        raise HTTPException(
            status_code=400,
            detail="Dataset name cannot be empty.",
        )

    try:
        result = ingest_dataset(
            db=db,
            uploaded_file=file,
            dataset_name=dataset_name,
            user_id=current_user.id,
            department_id=target_department_id,
        )

        return {
            "message": "Dataset uploaded and processed successfully.",
            "data": result,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception:
        logger.exception("Dataset upload and processing failed.")

        raise HTTPException(
            status_code=500,
            detail="Dataset processing failed. Check the backend logs.",
        )

    finally:
        file.file.close()


@router.get("", response_model=DatasetListResponse)
def get_datasets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve only datasets accessible to the current user."""

    query = db.query(Dataset)

    if current_user.role != "admin":
        if current_user.department_id is None:
            query = query.filter(Dataset.id == -1)
        else:
            query = query.filter(
                Dataset.department_id == current_user.department_id
            )

    total_records = query.count()

    offset = (page - 1) * page_size

    datasets = (
        query
        .order_by(
            Dataset.created_at.desc(),
            Dataset.id.desc(),
        )
        .offset(offset)
        .limit(page_size)
        .all()
    )

    total_pages = (
        (total_records + page_size - 1) // page_size
    )

    return {
        "data": datasets,
        "pagination": {
            "total_records": total_records,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        },
    }


@router.get(
    "/{dataset_id}",
    response_model=DatasetDetailResponse,
)
def get_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_accessible_dataset(
        db=db,
        dataset_id=dataset_id,
        current_user=current_user,
    )


@router.get(
    "/{dataset_id}/audit-logs",
    response_model=DatasetAuditLogListResponse,
)
def get_dataset_audit_logs(
    dataset_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve dataset audit history.

    Existing datasets use the normal dataset access rules.
    Deleted datasets use their final department recorded in audit history.
    """

    dataset = db.get(Dataset, dataset_id)

    if dataset is not None:
        # Enforces the normal department visibility rules, including
        # admin-only access to legacy datasets with no department.
        get_accessible_dataset(
            db=db,
            dataset_id=dataset_id,
            current_user=current_user,
        )

    audit_conditions = (
        AuditLog.entity_type == "dataset",
        AuditLog.entity_id == dataset_id,
    )

    if dataset is None:
        # A deleted dataset no longer has a database row. Its latest
        # department audit entry tells us which department owned it
        # immediately before deletion.
        latest_department_entry = db.scalar(
            select(AuditLog)
            .where(
                *audit_conditions,
                AuditLog.field_name == "department_id",
            )
            .order_by(
                AuditLog.changed_at.desc(),
                AuditLog.id.desc(),
            )
            .limit(1)
        )

        if latest_department_entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dataset audit history not found.",
            )

        if current_user.role == "admin":
            pass

        elif current_user.role == "employee":
            if current_user.department_id is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Dataset audit history not found.",
                )

            # A deletion event stores the department being deleted from
            # in old_value. Other events store the current department
            # in new_value.
            if latest_department_entry.action == "deleted":
                final_department_value = latest_department_entry.old_value
            else:
                final_department_value = latest_department_entry.new_value

            belongs_to_department = _department_value_matches(
                final_department_value,
                current_user.department_id,
            )

            if not belongs_to_department:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Dataset audit history not found.",
                )

        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Your account does not have permission "
                    "to view dataset audit history."
                ),
            )

    elif current_user.role not in {"admin", "employee"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Your account does not have permission "
                "to view dataset audit history."
            ),
        )

    total = db.scalar(
        select(func.count(AuditLog.id)).where(*audit_conditions)
    ) or 0

    rows = db.execute(
        select(AuditLog, User.name)
        .outerjoin(User, AuditLog.user_id == User.id)
        .where(*audit_conditions)
        .order_by(
            AuditLog.changed_at.desc(),
            AuditLog.id.desc(),
        )
        .offset(skip)
        .limit(limit)
    ).all()

    items = [
        DatasetAuditLogResponse(
            id=log.id,
            user_id=log.user_id,
            changed_by_name=user_name,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            field_name=log.field_name,
            old_value=log.old_value,
            new_value=log.new_value,
            changed_at=log.changed_at,
        )
        for log, user_name in rows
    ]

    return DatasetAuditLogListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{dataset_id}/sheets",
    response_model=list[DatasetSheetResponse],
)
def get_dataset_sheets(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_accessible_dataset(
        db=db,
        dataset_id=dataset_id,
        current_user=current_user,
    )

    return (
        db.query(DatasetSheet)
        .filter(DatasetSheet.dataset_id == dataset_id)
        .order_by(DatasetSheet.sheet_index.asc())
        .all()
    )


@router.patch(
    "/{dataset_id}",
    response_model=DatasetDetailResponse,
)
def update_dataset(
    dataset_id: int,
    payload: DatasetUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dataset = get_accessible_dataset(
        db=db,
        dataset_id=dataset_id,
        current_user=current_user,
    )

    require_dataset_editor(dataset, current_user)

    old_name = dataset.name
    new_name = payload.name.strip()

    if len(new_name) < 2:
        raise HTTPException(
            status_code=400,
            detail="Dataset name must contain at least 2 characters.",
        )

    dataset.name = new_name

    if old_name != new_name:
        record_audit_changes(
            db,
            user_id=current_user.id,
            entity_type="dataset",
            entity_id=dataset.id,
            action="updated",
            changes={
                "name": (old_name, new_name),
            },
        )

    db.commit()
    db.refresh(dataset)

    return dataset


@router.delete("/{dataset_id}")
def delete_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dataset = get_accessible_dataset(
        db=db,
        dataset_id=dataset_id,
        current_user=current_user,
    )

    require_dataset_editor(dataset, current_user)

    storage_path = dataset.storage_path

    # Preserve the dataset's final metadata in the generic audit log.
    # Do not use the dataset_id foreign-key field for this event:
    # generic entity references allow the history to survive deletion.
    record_audit_changes(
        db,
        user_id=current_user.id,
        entity_type="dataset",
        entity_id=dataset.id,
        action="deleted",
        changes={
            "name": (dataset.name, None),
            "owner_user_id": (dataset.user_id, None),
            "department_id": (dataset.department_id, None),
            "original_filename": (dataset.original_filename, None),
            "file_type": (dataset.file_type, None),
            "file_size": (dataset.file_size, None),
            "row_count": (dataset.row_count, None),
            "column_count": (dataset.column_count, None),
            "status": (dataset.status, None),
        },
    )

    db.delete(dataset)
    db.commit()

    # Only delete files located inside the application's upload directory.
    if storage_path:
        try:
            stored_file = Path(storage_path).resolve()
            upload_directory = UPLOAD_DIR.resolve()

            if (
                stored_file.is_relative_to(upload_directory)
                and stored_file.is_file()
            ):
                stored_file.unlink()

        except OSError:
            logger.exception(
                "Dataset was deleted, but its stored file could not be removed."
            )

    return {
        "message": "Dataset deleted successfully.",
        "dataset_id": dataset_id,
    }
