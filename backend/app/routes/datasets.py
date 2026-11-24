
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
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Dataset, DatasetSheet
from app.schemas.dataset import (
    DatasetListResponse,
    DatasetDetailResponse,
    DatasetSheetResponse,
)
from app.services.ingestion_service import ingest_dataset


router = APIRouter(
    prefix="/api/datasets",
    tags=["Datasets"],
)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

logger = logging.getLogger(__name__)


# --------------------------------------------------
# UPLOAD DATASET
# --------------------------------------------------

@router.post("/upload")
def upload_dataset(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    """Upload and ingest an Excel or CSV dataset."""

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="A filename is required.",
        )

    extension = Path(file.filename).suffix.lower()

    allowed_extensions = {
        ".xlsx",
        ".xlsm",
        ".xls",
        ".csv",
    }

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format.",
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

    try:
        result = ingest_dataset(
            db=db,
            uploaded_file=file,
            dataset_name=dataset_name,
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


# --------------------------------------------------
# GET ALL DATASETS
# --------------------------------------------------

@router.get(
    "",
    response_model=DatasetListResponse,
)
def get_datasets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Retrieve all datasets with pagination."""

    total_records = db.query(Dataset).count()

    offset = (page - 1) * page_size

    datasets = (
        db.query(Dataset)
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


# --------------------------------------------------
# GET ONE DATASET
# --------------------------------------------------

@router.get(
    "/{dataset_id}",
    response_model=DatasetDetailResponse,
)
def get_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
):
    """Retrieve a single dataset by its ID."""

    dataset = db.get(Dataset, dataset_id)

    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found.",
        )

    return dataset


# --------------------------------------------------
# GET DATASET WORKSHEETS
# --------------------------------------------------

@router.get(
    "/{dataset_id}/sheets",
    response_model=list[DatasetSheetResponse],
)
def get_dataset_sheets(
    dataset_id: int,
    db: Session = Depends(get_db),
):
    """Retrieve all worksheets belonging to a dataset."""

    # First, confirm that the dataset exists.
    dataset = db.get(Dataset, dataset_id)

    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found.",
        )

    # Retrieve worksheets belonging to this dataset only.
    sheets = (
        db.query(DatasetSheet)
        .filter(
            DatasetSheet.dataset_id == dataset_id
        )
        .order_by(
            DatasetSheet.sheet_index.asc()
        )
        .all()
    )

    return sheets
