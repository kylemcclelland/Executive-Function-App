"""Create users, inbox, tasks, steps, and daily priorities."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("timezone", sa.String(100), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("scheduled_date", sa.Date(), nullable=True),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint("status IN ('todo','in_progress','completed')", name="task_status"),
        sa.CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes > 0", name="task_estimate",
        ),
    )
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])
    op.create_index("ix_tasks_user_scheduled", "tasks", ["user_id", "scheduled_date"])
    op.create_table(
        "steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_completed", sa.Boolean(), nullable=False),
        sa.CheckConstraint("position >= 0", name="step_position"),
    )
    op.create_index("ix_steps_task_id", "steps", ["task_id"])
    op.create_table(
        "inbox_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("was_converted", sa.Boolean(), nullable=False),
        sa.Column(
            "converted_task_id", sa.Uuid(),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"), unique=True, nullable=True,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('unprocessed','processed','archived')", name="inbox_status",
        ),
    )
    op.create_index("ix_inbox_items_user_id", "inbox_items", ["user_id"])
    op.create_table(
        "daily_priorities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "date", "position", name="uq_priority_position"),
        sa.UniqueConstraint("user_id", "date", "task_id", name="uq_priority_task"),
        sa.CheckConstraint("position >= 0 AND position < 3", name="priority_limit"),
    )
    op.create_index("ix_daily_priorities_user_id", "daily_priorities", ["user_id"])
    op.create_index("ix_priorities_user_date", "daily_priorities", ["user_id", "date"])


def downgrade():
    for table in ("daily_priorities", "inbox_items", "steps", "tasks", "users"):
        op.drop_table(table)
