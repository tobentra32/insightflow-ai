
from datetime import datetime
import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMBaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DatasetResponse(ORMBaseSchema):
    id: int
    user_id: int | None = None
    department_id: int | None = None

    name: str
    original_filename: str
    file_type: str

    file_size: int
    row_count: int
    column_count: int

    status: str
    profile: dict[str, Any] | None = None

    created_at: datetime
    updated_at: datetime


class DatasetDetailResponse(DatasetResponse):
    pass


class DatasetUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)


class DatasetSheetResponse(ORMBaseSchema):
    id: int
    dataset_id: int

    sheet_name: str
    sheet_index: int

    row_count: int
    column_count: int

    profile: dict[str, Any] | None = None

    created_at: datetime


class DatasetColumnResponse(ORMBaseSchema):
    id: int
    sheet_id: int

    column_name: str
    column_index: int
    data_type: str

    is_unique: bool
    null_count: int


class DatasetRecordUpdateRequest(BaseModel):
    """A partial update containing one or more worksheet cell values."""

    model_config = ConfigDict(extra="forbid")

    changes: dict[str, Any] = Field(min_length=1, max_length=100)

    @field_validator("changes")
    @classmethod
    def validate_changes(cls, changes: dict[str, Any]) -> dict[str, Any]:
        def is_json_compatible(value: Any) -> bool:
            if value is None or isinstance(value, (str, bool, int)):
                return True

            if isinstance(value, float):
                return math.isfinite(value)

            if isinstance(value, list):
                return all(is_json_compatible(item) for item in value)

            if isinstance(value, dict):
                return all(
                    isinstance(key, str) and is_json_compatible(item)
                    for key, item in value.items()
                )

            return False

        for column_name, value in changes.items():
            if not column_name.strip() or len(column_name) > 255:
                raise ValueError("Invalid worksheet column name.")

            if not is_json_compatible(value):
                raise ValueError(
                    "Cell values must contain valid finite JSON data."
                )

        return changes


class DatasetRecordResponse(ORMBaseSchema):
    id: int
    sheet_id: int

    row_index: int
    data: dict[str, Any]

    created_at: datetime
    updated_at: datetime


class PaginationMetadata(BaseModel):
    total_records: int
    page: int
    page_size: int
    total_pages: int


class DatasetRecordListResponse(BaseModel):
    data: list[DatasetRecordResponse]
    pagination: PaginationMetadata


class DatasetListResponse(BaseModel):
    data: list[DatasetResponse]
    pagination: PaginationMetadata


class DatasetAuditLogResponse(BaseModel):
    id: int
    user_id: int | None
    changed_by_name: str | None
    action: str | None
    entity_type: str | None
    entity_id: int | None
    field_name: str
    old_value: Any | None
    new_value: Any | None
    changed_at: datetime


class DatasetAuditLogListResponse(BaseModel):
    items: list[DatasetAuditLogResponse]
    total: int
    skip: int
    limit: int


class DatasetRecordAuditLogResponse(BaseModel):
    id: int
    user_id: int | None
    changed_by_name: str | None
    action: str | None
    entity_type: str
    entity_id: int
    field_name: str
    old_value: Any | None
    new_value: Any | None
    changed_at: datetime


class DatasetRecordAuditLogListResponse(BaseModel):
    items: list[DatasetRecordAuditLogResponse]
    total: int
    skip: int
    limit: int
