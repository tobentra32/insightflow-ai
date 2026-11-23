
from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    BigInteger,
    ForeignKey,
    DateTime,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    file_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )

    storage_path: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True
    )

    file_size: Mapped[int] = mapped_column(
        BigInteger,
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

    status: Mapped[str] = mapped_column(
        String(30),
        server_default=text("'uploaded'"),
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

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    owner: Mapped["User | None"] = relationship(
        back_populates="datasets"
    )

    sheets: Mapped[list["DatasetSheet"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        passive_deletes=True
    )
