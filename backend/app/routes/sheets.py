
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.permissions import get_accessible_sheet
from app.database import get_db
from app.models.dataset_column import DatasetColumn
from app.models.record import DatasetRecord
from app.models.user import User
from app.schemas.dataset import (
    DatasetColumnResponse,
    DatasetRecordListResponse,
)


router = APIRouter(
    prefix="/api/sheets",
    tags=["Sheets"],
)


@router.get(
    "/{sheet_id}/columns",
    response_model=list[DatasetColumnResponse],
)
def get_sheet_columns(
    sheet_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve columns only if the parent dataset is accessible."""

    get_accessible_sheet(
        db=db,
        sheet_id=sheet_id,
        current_user=current_user,
    )

    return (
        db.query(DatasetColumn)
        .filter(DatasetColumn.sheet_id == sheet_id)
        .order_by(DatasetColumn.column_index.asc())
        .all()
    )


@router.get(
    "/{sheet_id}/records",
    response_model=DatasetRecordListResponse,
)
def get_sheet_records(
    sheet_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve records only if the parent dataset is accessible."""

    get_accessible_sheet(
        db=db,
        sheet_id=sheet_id,
        current_user=current_user,
    )

    query = db.query(DatasetRecord).filter(
        DatasetRecord.sheet_id == sheet_id
    )

    total_records = query.count()
    offset = (page - 1) * page_size

    records = (
        query
        .order_by(DatasetRecord.row_index.asc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

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
