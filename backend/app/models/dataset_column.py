
from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DatasetColumn(Base):
    __tablename__ = "dataset_columns"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    column_name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    data_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    is_unique: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    null_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    dataset = relationship("Dataset", back_populates="columns")
