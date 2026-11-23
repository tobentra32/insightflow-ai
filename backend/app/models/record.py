
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Integer,
    ForeignKey,
    DateTime,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DatasetRecord(Base):
    __tablename__ = "dataset_records"

    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "row_index",
            name="uq_dataset_record_row"
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True
    )

    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    row_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

  

    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="record"
    )

    sheet_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_sheets.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    sheet: Mapped["DatasetSheet"] = relationship(
        back_populates="records"
    )
