
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime, ForeignKey, Integer
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DatasetRecord(Base):
    __tablename__ = "dataset_records"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )

    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    data: Mapped[dict] = mapped_column(
        JSONB, nullable=False
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

    dataset = relationship("Dataset", back_populates="records")

    audit_logs = relationship(
        "AuditLog",
        back_populates="record",
        cascade="all, delete-orphan",
    )
