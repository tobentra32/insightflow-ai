from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    ForeignKey,
    DateTime,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base



class DatasetSheet(Base):
    __tablename__ = "dataset_sheets"

    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "sheet_name",
            name="uq_dataset_sheet_name"
        ),
        UniqueConstraint(
            "dataset_id",
            "sheet_index",
            name="uq_dataset_sheet_index"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    sheet_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    sheet_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    row_count: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
        nullable=False
    )

    column_count: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
        nullable=False
    )

    profile: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    dataset: Mapped["Dataset"] = relationship(
        back_populates="sheets"
    )

    columns: Mapped[list["DatasetColumn"]] = relationship(
        back_populates="sheet",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    records: Mapped[list["DatasetRecord"]] = relationship(
        back_populates="sheet",
        cascade="all, delete-orphan",
        passive_deletes=True
    )