
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


UserRole = Literal["admin", "employee"]


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


class AdminUserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    role: UserRole = "employee"
    department_id: int | None = None


class AdminUserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    email: EmailStr | None = None
    role: UserRole | None = None
    department_id: int | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be supplied.")

        for field in ("name", "email", "role", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")

        return self


class AdminUserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    department_id: int | None
    department_name: str | None
    is_active: bool
    must_change_password: bool
    created_at: datetime


class AdminUserCreatedResponse(BaseModel):
    message: str
    user: AdminUserResponse
    temporary_password: str


class PasswordResetResponse(BaseModel):
    message: str
    temporary_password: str
    must_change_password: bool
