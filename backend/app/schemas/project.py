from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ProjectStatus = Literal["active", "on_hold", "completed", "archived"]


class ProjectCreateRequest(BaseModel):
    customer_name: str = Field(min_length=2, max_length=200)
    destination: str = Field(min_length=2, max_length=200)
    contract_reference: str | None = Field(default=None, max_length=150)
    description: str | None = None
    department_id: int | None = Field(default=None, gt=0)

    @field_validator("customer_name", "destination")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        return value

    @field_validator("contract_reference", "description")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ProjectUpdateRequest(BaseModel):
    customer_name: str | None = Field(default=None, min_length=2, max_length=200)
    destination: str | None = Field(default=None, min_length=2, max_length=200)
    contract_reference: str | None = Field(default=None, max_length=150)
    description: str | None = None
    department_id: int | None = Field(default=None, gt=0)
    status: ProjectStatus | None = None

    @field_validator("customer_name", "destination")
    @classmethod
    def validate_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        return value

    @field_validator("contract_reference", "description")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")

        for field in ("customer_name", "destination", "status", "department_id"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")

        return self


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    department_id: int
    created_by: int
    customer_name: str
    destination: str
    contract_reference: str | None
    description: str | None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
