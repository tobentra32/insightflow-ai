
"""add departments and access control

Revision ID: 72e35e9acbd2
Revises: 314e79d7b420
Create Date: 2026-11-24 14:03:33.235596

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Revision identifiers.
revision: str = "72e35e9acbd2"
down_revision: Union[str, Sequence[str], None] = "314e79d7b420"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply department and access-control schema changes."""

    # --------------------------------------------------
    # DEPARTMENTS
    # --------------------------------------------------

    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_departments_id",
        "departments",
        ["id"],
        unique=False,
    )

    op.create_index(
        "ix_departments_name",
        "departments",
        ["name"],
        unique=True,
    )

    # --------------------------------------------------
    # DATASET DEPARTMENT OWNERSHIP
    # --------------------------------------------------

    op.add_column(
        "datasets",
        sa.Column("department_id", sa.Integer(), nullable=True),
    )

    op.create_index(
        "ix_datasets_department_id",
        "datasets",
        ["department_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_datasets_department_id_departments",
        "datasets",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --------------------------------------------------
    # USER ACCESS CONTROL
    # --------------------------------------------------

    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=30),
            server_default=sa.text("'employee'"),
            nullable=False,
        ),
    )

    op.add_column(
        "users",
        sa.Column("department_id", sa.Integer(), nullable=True),
    )

    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )

    op.create_check_constraint(
        "ck_users_valid_role",
        "users",
        "role IN ('admin', 'employee')",
    )

    op.create_index(
        "ix_users_department_id",
        "users",
        ["department_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_users_department_id_departments",
        "users",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Reverse department and access-control schema changes."""

    # Remove user department relationship and access controls.
    op.drop_constraint(
        "fk_users_department_id_departments",
        "users",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_users_department_id",
        table_name="users",
    )

    op.drop_constraint(
        "ck_users_valid_role",
        "users",
        type_="check",
    )

    op.drop_column("users", "must_change_password")
    op.drop_column("users", "is_active")
    op.drop_column("users", "department_id")
    op.drop_column("users", "role")

    # Remove dataset department relationship.
    op.drop_constraint(
        "fk_datasets_department_id_departments",
        "datasets",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_datasets_department_id",
        table_name="datasets",
    )

    op.drop_column("datasets", "department_id")

    # Remove departments table.
    op.drop_index(
        "ix_departments_name",
        table_name="departments",
    )

    op.drop_index(
        "ix_departments_id",
        table_name="departments",
    )

    op.drop_table("departments")
