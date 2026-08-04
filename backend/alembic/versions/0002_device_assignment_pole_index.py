"""Index current device lookups by pole.

Revision ID: 0002
"""

from alembic import op


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_device_assignments_pole_current", "device_assignments", ["pole_id", "effective_to"])


def downgrade() -> None:
    op.drop_index("ix_device_assignments_pole_current", table_name="device_assignments")
