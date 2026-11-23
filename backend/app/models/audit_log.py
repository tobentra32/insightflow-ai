
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime, ForeignKey, Integer, String
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    record_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    field_name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    old_value: Mapped[dict] = mapped_column(
        JSONB, nullable=False
    )

    new_value: Mapped[dict] = mapped_column(
        JSONB, nullable=False
    )

    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    record = relationship(
        "DatasetRecord", back_populates="audit_logs"
    )
