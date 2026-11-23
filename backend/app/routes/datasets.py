
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.ingestion_service import ingest_dataset


router = APIRouter(
    prefix="/api/datasets",
    tags=["Datasets"],
)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


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

    dataset_name = (
        name.strip()
        if name and name.strip()
        else Path(file.filename).stem
    )

    try:
        result = ingest_dataset(
            db=db,
            filename=file.filename,
            dataset_name=dataset_name,
            file_bytes=file_bytes,
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

    except Exception as exc:
        # The detailed exception should be logged server-side.
        raise HTTPException(
            status_code=500,
            detail="Dataset processing failed.",
        ) from exc
