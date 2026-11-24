
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.dataset_sheet import DatasetSheet
from app.models.dataset_column import DatasetColumn
from app.models.record import DatasetRecord

from app.schemas.dataset import (
    DatasetColumnResponse,
    DatasetRecordListResponse,
)


router = APIRouter(
    prefix="/api/sheets",
    tags=["Sheets"],
)


# --------------------------------------------------
# GET SHEET COLUMNS
# --------------------------------------------------

@router.get(
    "/{sheet_id}/columns",
    response_model=list[DatasetColumnResponse],
)
def get_sheet_columns(
    sheet_id: int,
    db: Session = Depends(get_db),
):
    """Retrieve all columns belonging to a worksheet."""

    sheet = db.get(DatasetSheet, sheet_id)

    if sheet is None:
        raise HTTPException(
            status_code=404,
            detail="Worksheet not found.",
        )

    columns = (
        db.query(DatasetColumn)
        .filter(
            DatasetColumn.sheet_id == sheet_id
        )
        .order_by(
            DatasetColumn.column_index.asc()
        )
        .all()
    )

    return columns


# --------------------------------------------------
# GET SHEET RECORDS
# --------------------------------------------------

@router.get(
    "/{sheet_id}/records",
    response_model=DatasetRecordListResponse,
)
def get_sheet_records(
    sheet_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Retrieve worksheet records with pagination."""

    # First, check whether the worksheet exists.
    sheet = db.get(DatasetSheet, sheet_id)

    if sheet is None:
        raise HTTPException(
            status_code=404,
            detail="Worksheet not found.",
        )

    # Count all records belonging to this worksheet.
    total_records = (
        db.query(DatasetRecord)
        .filter(
            DatasetRecord.sheet_id == sheet_id
        )
        .count()
    )

    # Calculate how many records to skip.
    offset = (page - 1) * page_size

    # Retrieve the requested page of records.
    records = (
        db.query(DatasetRecord)
        .filter(
            DatasetRecord.sheet_id == sheet_id
        )
        .order_by(
            DatasetRecord.row_index.asc()
        )
        .offset(offset)
        .limit(page_size)
        .all()
    )

    # Calculate the total number of pages.
    total_pages = (
        (total_records + page_size - 1) // page_size
    )

    return {
        "data": records,
        "pagination": {
            "total_records": total_records,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        },
    }
