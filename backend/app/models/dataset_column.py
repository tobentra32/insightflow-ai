
from sqlalchemy import (
    String,
    Integer,
    Boolean,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DatasetColumn(Base):
    __tablename__ = "dataset_columns"

    __table_args__ = (
        UniqueConstraint(
            "sheet_id",
            "column_index",
            name="uq_sheet_column_index"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    sheet_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_sheets.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    column_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    column_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    data_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    is_unique: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    null_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )

    sheet: Mapped["DatasetSheet"] = relationship(
        back_populates="columns"
    )
