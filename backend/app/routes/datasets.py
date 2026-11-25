
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
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.permissions import (
    get_accessible_dataset,
    require_dataset_editor,
)
from app.database import get_db
from app.models import Dataset, DatasetSheet, User
from app.models.department import Department
from app.schemas.dataset import (
    DatasetListResponse,
    DatasetDetailResponse,
    DatasetSheetResponse,
    DatasetUpdateRequest,
)
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
                detail="Your account must be assigned to a department before uploading datasets.",
            )

        if (
            department_id is not None
            and department_id != current_user.department_id
        ):
            raise HTTPException(
                status_code=403,
                detail="You can only upload datasets into your own department.",
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

    dataset.name = payload.name.strip()

    if len(dataset.name) < 2:
        raise HTTPException(
            status_code=400,
            detail="Dataset name must contain at least 2 characters.",
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
