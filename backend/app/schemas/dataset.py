
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
