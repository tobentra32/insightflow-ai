"""Add generic entity fields to audit logs.

Revision ID: 28c4a9e71b62
Revises: 17ae4e575b87
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "28c4a9e71b62"
down_revision: Union[str, None] = "17ae4e575b87"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column(
            "action",
            sa.String(length=50),
            nullable=True,
        ),
    )

    op.add_column(
        "audit_logs",
        sa.Column(
            "entity_type",
            sa.String(length=50),
            nullable=True,
        ),
    )

    op.add_column(
        "audit_logs",
        sa.Column(
            "entity_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_audit_logs_action",
        "audit_logs",
        ["action"],
        unique=False,
    )

    op.create_index(
        "ix_audit_logs_entity_type",
        "audit_logs",
        ["entity_type"],
        unique=False,
    )

    op.create_index(
        "ix_audit_logs_entity_id",
        "audit_logs",
        ["entity_id"],
        unique=False,
    )

    op.create_index(
        "ix_audit_logs_entity_type_entity_id_changed_at",
        "audit_logs",
        ["entity_type", "entity_id", "changed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_audit_logs_entity_type_entity_id_changed_at",
        table_name="audit_logs",
    )

    op.drop_index(
        "ix_audit_logs_entity_id",
        table_name="audit_logs",
    )

    op.drop_index(
        "ix_audit_logs_entity_type",
        table_name="audit_logs",
    )

    op.drop_index(
        "ix_audit_logs_action",
        table_name="audit_logs",
    )

    op.drop_column("audit_logs", "entity_id")
    op.drop_column("audit_logs", "entity_type")
    op.drop_column("audit_logs", "action")