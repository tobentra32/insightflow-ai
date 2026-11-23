
from datetime import datetime
from typing import Any

from sqlalchemy import (
    String,
    ForeignKey,
    DateTime,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True
    )

    dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    record_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    field_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    old_value: Mapped[Any | None] = mapped_column(
        JSONB,
        nullable=True
    )

    new_value: Mapped[Any | None] = mapped_column(
        JSONB,
        nullable=True
    )

    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    record: Mapped["DatasetRecord | None"] = relationship(
        back_populates="audit_logs"
    )
