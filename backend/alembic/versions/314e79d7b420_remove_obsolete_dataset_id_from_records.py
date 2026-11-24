"""remove obsolete dataset_id from records

Revision ID: 314e79d7b420
Revises: 790b594b88a1
Create Date: 2026-11-24 10:26:41.808506

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '314e79d7b420'
down_revision: Union[str, Sequence[str], None] = '790b594b88a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove the old foreign key first.
    op.drop_constraint(
        "dataset_records_dataset_id_fkey",
        "dataset_records",
        type_="foreignkey",
    )

    # Remove the obsolete dataset_id column.
    op.drop_column(
        "dataset_records",
        "dataset_id",
    )


def downgrade() -> None:
    # Restore dataset_id as a nullable column.
    op.add_column(
        "dataset_records",
        sa.Column(
            "dataset_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    # Recover dataset_id through the worksheet relationship.
    op.execute("""
        UPDATE dataset_records AS records
        SET dataset_id = sheets.dataset_id
        FROM dataset_sheets AS sheets
        WHERE records.sheet_id = sheets.id
    """)

    # Restore the original NOT NULL requirement.
    op.alter_column(
        "dataset_records",
        "dataset_id",
        nullable=False,
    )

    # Restore the foreign key.
    op.create_foreign_key(
        "dataset_records_dataset_id_fkey",
        "dataset_records",
        "datasets",
        ["dataset_id"],
        ["id"],
        ondelete="CASCADE",
    )
