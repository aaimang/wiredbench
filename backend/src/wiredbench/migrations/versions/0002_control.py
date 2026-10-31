"""view-as sessions and mock API keys

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

import wiredbench.models

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("auth_session") as batch:
        batch.add_column(sa.Column("view_as", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "mock_api_key",
        sa.Column("sandbox_id", sa.Integer(), nullable=False),
        sa.Column("read_hash", sa.String(length=64), nullable=False),
        sa.Column("write_hash", sa.String(length=64), nullable=False),
        sa.Column("allow_mass_deletion", sa.Boolean(), nullable=False),
        sa.Column("created_at", wiredbench.models.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["sandbox_id"], ["sandbox.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("sandbox_id"),
    )


def downgrade() -> None:
    op.drop_table("mock_api_key")
    with op.batch_alter_table("auth_session") as batch:
        batch.drop_column("view_as")
