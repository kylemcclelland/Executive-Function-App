"""Align task step and priority date names without losing existing data."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.rename_table("steps", "task_steps")
    op.drop_index("ix_steps_task_id", table_name="task_steps")
    op.create_index("ix_task_steps_task_id", "task_steps", ["task_id"])
    op.alter_column("daily_priorities", "date", new_column_name="priority_date",
                    existing_type=sa.Date(), existing_nullable=False)


def downgrade():
    op.alter_column("daily_priorities", "priority_date", new_column_name="date",
                    existing_type=sa.Date(), existing_nullable=False)
    op.drop_index("ix_task_steps_task_id", table_name="task_steps")
    op.create_index("ix_steps_task_id", "task_steps", ["task_id"])
    op.rename_table("task_steps", "steps")
