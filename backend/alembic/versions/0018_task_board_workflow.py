# ruff: noqa: E501
"""Task board workflow: two new unfinished statuses (in_review, blocked) and their details.

Additive: the tasks.status CHECK gains 'in_review' and 'blocked' (both mean unfinished everywhere,
exactly like 'todo'; 'completed' keeps meaning done), and seven nullable columns record why a task
is blocked, where it came from, and its review trail. No row is changed and no status is rewritten:
existing 'todo'/'in_progress'/'completed' values are already the board's To Do, In Progress and Done.

On PostgreSQL (production) everything is a plain ALTER: no table is rebuilt. On SQLite (tests,
local development) swapping a CHECK rebuilds the table, and dropping the old one fires the
ON DELETE CASCADE / SET NULL of its dependents, so their rows are captured first and restored
after — nothing is lost. Down: reverses both (only safe while no task uses the new statuses).
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

OLD = "status IN ('todo','in_progress','completed')"
NEW = "status IN ('todo','in_progress','in_review','blocked','completed')"
CASCADE_DEPENDENTS = ("task_steps", "daily_priorities")                  # rows vanish with the parent
SET_NULL_DEPENDENTS = (("inbox_items", "converted_task_id"), ("work_sessions", "task_id"))


def board_columns() -> list[sa.Column]:
    return [
        sa.Column("previous_status", sa.String(20), nullable=True),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("waiting_on", sa.String(300), nullable=True),
        sa.Column("blocked_follow_up", sa.Date(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("reviewer_name", sa.String(200), nullable=True),
        sa.Column("review_requested_at", sa.DateTime(timezone=True), nullable=True),
    ]


def capture_dependents(bind):
    """Everything SQLite's tasks-table rebuild would cascade away or null out."""
    meta = sa.MetaData()
    kept = {}
    for name in CASCADE_DEPENDENTS:
        table = sa.Table(name, meta, autoload_with=bind)
        kept[name] = (table, [dict(row._mapping) for row in bind.execute(sa.select(table))])
    links = {}
    for name, column in SET_NULL_DEPENDENTS:
        table = sa.Table(name, meta, autoload_with=bind)
        links[name] = (table, column, {
            row.id: getattr(row, column)
            for row in bind.execute(sa.select(table.c.id, table.c[column])) if getattr(row, column)
        })
    return kept, links


def restore_dependents(bind, kept, links):
    for table, rows in kept.values():
        present = {row.id for row in bind.execute(sa.select(table.c.id))}
        missing = [row for row in rows if row["id"] not in present]
        if missing:
            bind.execute(table.insert(), missing)
    for table, column, values in links.values():
        for row_id, value in values.items():
            bind.execute(table.update().where(table.c.id == row_id).values(**{column: value}))


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        kept, links = capture_dependents(bind)
        with op.batch_alter_table("tasks") as batch:
            batch.drop_constraint("task_status", type_="check")
            batch.create_check_constraint("task_status", NEW)
            for column in board_columns():
                batch.add_column(column)
        restore_dependents(bind, kept, links)
        return
    op.drop_constraint("task_status", "tasks", type_="check")
    op.create_check_constraint("task_status", "tasks", NEW)
    for column in board_columns():
        op.add_column("tasks", column)


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        kept, links = capture_dependents(bind)
        with op.batch_alter_table("tasks") as batch:
            for column in reversed(board_columns()):
                batch.drop_column(column.name)
            batch.drop_constraint("task_status", type_="check")
            batch.create_check_constraint("task_status", OLD)
        restore_dependents(bind, kept, links)
        return
    for column in reversed(board_columns()):
        op.drop_column("tasks", column.name)
    op.drop_constraint("task_status", "tasks", type_="check")
    op.create_check_constraint("task_status", "tasks", OLD)
