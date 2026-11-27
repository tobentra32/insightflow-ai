
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy import Numeric, and_, case, cast, func
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.permissions import (
    get_accessible_sheet,
    require_dataset_editor,
)
from app.database import get_db
from app.models.dataset_column import DatasetColumn
from app.models.record import DatasetRecord
from app.models.user import User
from app.schemas.dataset import (
    DatasetColumnResponse,
    DatasetRecordAuditLogListResponse,
    DatasetRecordAuditLogResponse,
    DatasetRecordListResponse,
    DatasetRecordResponse,
    DatasetRecordUpdateRequest,
)
from app.services.audit import record_audit_changes
from app.services.audit_history import get_audit_history


router = APIRouter(
    prefix="/api/sheets",
    tags=["Sheets"],
)


# Numeric text is deliberately bounded to avoid PostgreSQL NUMERIC
# conversion errors caused by excessively large values or exponents.
NUMERIC_PATTERN = (
    r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
    r"(?:[eE][+-]?[0-9]{1,4})?$"
)

MAX_NUMERIC_TEXT_LENGTH = 1000
MAX_NUMERIC_DIGITS = 1000
MAX_NUMERIC_EXPONENT = 11000

NUMERIC_DATA_TYPES = {
    "number",
    "numeric",
    "integer",
    "int",
    "float",
    "decimal",
    "double",
}

SUPPORTED_OPERATORS = {
    "eq",
    "ne",
    "contains",
    "gt",
    "gte",
    "lt",
    "lte",
    "isnull",
}

MAX_FILTERS = 20


def _validate_numeric_value(value: Any) -> Decimal:
    """Convert a filter value to a bounded, finite Decimal."""

    if isinstance(value, bool):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Numeric filters require a numeric value.",
        )

    try:
        number = Decimal(str(value))

        if not number.is_finite():
            raise InvalidOperation

        decimal_tuple = number.as_tuple()

        if len(decimal_tuple.digits) > MAX_NUMERIC_DIGITS:
            raise InvalidOperation

        if abs(decimal_tuple.exponent) > MAX_NUMERIC_EXPONENT:
            raise InvalidOperation

        if abs(number.adjusted()) > MAX_NUMERIC_EXPONENT:
            raise InvalidOperation

        return number

    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Numeric comparison filters require "
                "a valid finite number within the supported range."
            ),
        )


def _numeric_value_expression(value_expression):
    """
    Safely convert numeric-looking text into PostgreSQL NUMERIC.

    Both the numeric pattern and maximum text length must match
    before PostgreSQL attempts the cast.
    """

    is_safe_numeric = and_(
        func.length(value_expression) <= MAX_NUMERIC_TEXT_LENGTH,
        value_expression.op("~")(NUMERIC_PATTERN),
    )

    return case(
        (
            is_safe_numeric,
            cast(value_expression, Numeric),
        ),
        else_=None,
    )


def parse_filters(
    filters: str | None,
) -> dict[str, dict[str, Any]]:
    """Parse and validate the JSON filter parameter."""

    if filters is None:
        return {}

    try:
        parsed = json.loads(filters)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Filters must contain valid JSON.",
        )

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Filters must be a JSON object.",
        )

    if len(parsed) > MAX_FILTERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"A maximum of {MAX_FILTERS} filters is allowed.",
        )

    validated = {}

    for column_name, conditions in parsed.items():
        if (
            not isinstance(column_name, str)
            or not column_name.strip()
            or len(column_name) > 255
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid filter column name.",
            )

        if not isinstance(conditions, dict) or not conditions:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid conditions for column '{column_name}'.",
            )

        for operator, value in conditions.items():
            if operator not in SUPPORTED_OPERATORS:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Unsupported filter operator: {operator}.",
                )

            if operator == "contains":
                if not isinstance(value, str) or len(value) > 500:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=(
                            "The contains operator requires a string "
                            "of at most 500 characters."
                        ),
                    )

            elif operator == "isnull":
                if not isinstance(value, bool):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="The isnull operator requires a boolean.",
                    )

            elif operator in {"gt", "gte", "lt", "lte"}:
                _validate_numeric_value(value)

            elif isinstance(value, (dict, list)):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Filter values must be simple values.",
                )

        validated[column_name] = conditions

    return validated


def apply_record_filters(
    query,
    filters: dict[str, dict[str, Any]],
):
    """Apply validated filters against PostgreSQL JSONB data."""

    for column_name, conditions in filters.items():
        value_expression = DatasetRecord.data[column_name].astext

        for operator, expected_value in conditions.items():

            if operator == "eq":
                if expected_value is None:
                    query = query.filter(
                        value_expression.is_(None)
                    )
                    continue

                expected = (
                    str(expected_value).lower()
                    if isinstance(expected_value, bool)
                    else str(expected_value)
                )

                query = query.filter(
                    value_expression == expected
                )

            elif operator == "ne":
                if expected_value is None:
                    query = query.filter(
                        value_expression.isnot(None)
                    )
                    continue

                expected = (
                    str(expected_value).lower()
                    if isinstance(expected_value, bool)
                    else str(expected_value)
                )

                query = query.filter(
                    value_expression.isnot(None),
                    value_expression != expected,
                )

            elif operator == "contains":
                query = query.filter(
                    func.lower(value_expression).contains(
                        expected_value.lower(),
                        autoescape=True,
                    )
                )

            elif operator == "isnull":
                if expected_value:
                    query = query.filter(
                        value_expression.is_(None)
                    )
                else:
                    query = query.filter(
                        value_expression.isnot(None)
                    )

            elif operator in {"gt", "gte", "lt", "lte"}:
                numeric_expression = _numeric_value_expression(
                    value_expression
                )

                expected = _validate_numeric_value(expected_value)

                if operator == "gt":
                    query = query.filter(
                        numeric_expression > expected
                    )

                elif operator == "gte":
                    query = query.filter(
                        numeric_expression >= expected
                    )

                elif operator == "lt":
                    query = query.filter(
                        numeric_expression < expected
                    )

                elif operator == "lte":
                    query = query.filter(
                        numeric_expression <= expected
                    )

    return query


def refresh_column_metadata(
    db: Session,
    *,
    sheet_id: int,
    column: DatasetColumn,
) -> None:
    """Recalculate null and uniqueness metadata after a cell is edited."""

    value_expression = DatasetRecord.data[column.column_name].astext

    total_count, non_null_count, distinct_count = (
        db.query(
            func.count(DatasetRecord.id),
            func.count(value_expression),
            func.count(func.distinct(value_expression)),
        )
        .filter(DatasetRecord.sheet_id == sheet_id)
        .one()
    )

    column.null_count = total_count - non_null_count
    column.is_unique = (
        non_null_count > 0
        and distinct_count == non_null_count
    )


def apply_record_sorting(
    query,
    sort_column: DatasetColumn | None,
    sort_order: str,
):
    """
    Sort records using the worksheet column's declared data type.

    Invalid numeric values sort as NULL rather than causing a
    database conversion error. NULL values are placed last.

    Record ID provides a final deterministic tie-breaker.
    """

    if sort_column is None:
        return query.order_by(
            DatasetRecord.row_index.asc(),
            DatasetRecord.id.asc(),
        )

    value_expression = DatasetRecord.data[
        sort_column.column_name
    ].astext

    data_type = (sort_column.data_type or "").strip().lower()

    if data_type in NUMERIC_DATA_TYPES:
        sort_expression = _numeric_value_expression(
            value_expression
        )
    else:
        sort_expression = func.lower(value_expression)

    if sort_order == "desc":
        ordering = sort_expression.desc().nullslast()
    else:
        ordering = sort_expression.asc().nullslast()

    return query.order_by(
        ordering,
        DatasetRecord.row_index.asc(),
        DatasetRecord.id.asc(),
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
    filters: str | None = Query(default=None),
    sort_by: str | None = Query(default=None, min_length=1, max_length=255),
    sort_order: str = Query(
        default="asc",
        pattern="^(asc|desc)$",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve worksheet records with filtering, sorting and pagination.

    Filtering and sorting happen in PostgreSQL before pagination.
    """

    sheet, _ = get_accessible_sheet(
        db=db,
        sheet_id=sheet_id,
        current_user=current_user,
    )

    parsed_filters = parse_filters(filters)

    requested_columns = set(parsed_filters.keys())

    if sort_by is not None:
        requested_columns.add(sort_by)

    available_columns = {}

    if requested_columns:
        columns = (
            db.query(DatasetColumn)
            .filter(DatasetColumn.sheet_id == sheet_id)
            .all()
        )

        available_columns = {
            column.column_name: column
            for column in columns
        }

        invalid_columns = (
            requested_columns - set(available_columns.keys())
        )

        if invalid_columns:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": (
                        "One or more requested columns do not exist "
                        "in this worksheet."
                    ),
                    "invalid_columns": sorted(invalid_columns),
                },
            )

    sort_column = (
        available_columns.get(sort_by)
        if sort_by is not None
        else None
    )

    query = db.query(DatasetRecord).filter(
        DatasetRecord.sheet_id == sheet.id
    )

    query = apply_record_filters(
        query,
        parsed_filters,
    )

    total_records = query.count()

    query = apply_record_sorting(
        query,
        sort_column,
        sort_order,
    )

    offset = (page - 1) * page_size

    records = (
        query
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


@router.patch(
    "/{sheet_id}/records/{record_id}",
    response_model=DatasetRecordResponse,
)
def update_sheet_record(
    sheet_id: int,
    record_id: int,
    payload: DatasetRecordUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update selected cells in one record and audit every changed value.

    Employees may edit only datasets they originally uploaded. Administrators
    may edit datasets across departments. Other worksheet columns and record
    metadata are not accepted from the request.
    """

    sheet, dataset = get_accessible_sheet(
        db=db,
        sheet_id=sheet_id,
        current_user=current_user,
    )

    require_dataset_editor(dataset, current_user)

    record = (
        db.query(DatasetRecord)
        .filter(
            DatasetRecord.id == record_id,
            DatasetRecord.sheet_id == sheet.id,
        )
        .with_for_update()
        .first()
    )

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Record not found in this worksheet.",
        )

    columns = (
        db.query(DatasetColumn)
        .filter(DatasetColumn.sheet_id == sheet.id)
        .all()
    )
    available_columns = {
        column.column_name: column
        for column in columns
    }

    requested_column_names = set(payload.changes)
    invalid_columns = requested_column_names - set(available_columns)

    if invalid_columns:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "One or more columns do not exist in this worksheet.",
                "invalid_columns": sorted(invalid_columns),
            },
        )

    updated_data = dict(record.data)
    audit_changes = {}

    for column_name, new_value in payload.changes.items():
        old_value = updated_data.get(column_name)

        if old_value == new_value:
            continue

        audit_changes[column_name] = (old_value, new_value)
        updated_data[column_name] = new_value

    if audit_changes:
        record.data = updated_data

        # Persist the edited JSONB value within the current transaction before
        # calculating metadata, so the aggregate query includes this edit.
        db.flush()

        # Lock affected column metadata in a consistent order. This prevents
        # concurrent edits to different records from overwriting each other's
        # null-count or uniqueness calculations with stale results.
        locked_columns = (
            db.query(DatasetColumn)
            .filter(
                DatasetColumn.sheet_id == sheet.id,
                DatasetColumn.column_name.in_(audit_changes.keys()),
            )
            .order_by(DatasetColumn.id.asc())
            .with_for_update()
            .all()
        )
        locked_columns_by_name = {
            column.column_name: column
            for column in locked_columns
        }

        for column_name in sorted(audit_changes):
            refresh_column_metadata(
                db,
                sheet_id=sheet.id,
                column=locked_columns_by_name[column_name],
            )

        record_audit_changes(
            db,
            user_id=current_user.id,
            entity_type="dataset_record",
            entity_id=record.id,
            action="updated",
            record_id=record.id,
            changes=audit_changes,
        )

        db.commit()
        db.refresh(record)

    return record


@router.get(
    "/{sheet_id}/records/{record_id}/audit-logs",
    response_model=DatasetRecordAuditLogListResponse,
)
def get_sheet_record_audit_logs(
    sheet_id: int,
    record_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve the change history for one record in an accessible sheet."""

    sheet, _ = get_accessible_sheet(
        db=db,
        sheet_id=sheet_id,
        current_user=current_user,
    )

    record = (
        db.query(DatasetRecord)
        .filter(
            DatasetRecord.id == record_id,
            DatasetRecord.sheet_id == sheet.id,
        )
        .first()
    )

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Record not found in this worksheet.",
        )

    history = get_audit_history(
        db,
        entity_type="dataset_record",
        entity_id=record.id,
        skip=skip,
        limit=limit,
    )

    return DatasetRecordAuditLogListResponse(
        items=[
            DatasetRecordAuditLogResponse(**item)
            for item in history.items
        ],
        total=history.total,
        skip=skip,
        limit=limit,
    )
