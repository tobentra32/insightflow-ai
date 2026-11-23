
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime, ForeignKey, Integer, String, BigInteger
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    original_filename: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    file_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )

    storage_path: Mapped[str] = mapped_column(
        String(500), nullable=False
    )

    file_size: Mapped[int] = mapped_column(
        BigInteger, nullable=False
    )

    row_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    column_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    owner = relationship("User", back_populates="datasets")

    columns = relationship(
        "DatasetColumn",
        back_populates="dataset",
        cascade="all, delete-orphan",
    )

    records = relationship(
        "DatasetRecord",
        back_populates="dataset",
        cascade="all, delete-orphan",
    )
