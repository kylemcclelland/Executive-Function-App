# ruff: noqa: E501
"""Which surface manages a task: the Daily Checklist or the Task Board.

Additive: one NOT NULL column ``task_kind`` ('checklist' or 'board', with a CHECK) whose server
default makes every existing task a checklist item — the conservative choice, since before this
migration every task lived on the simple list and no board-only evidence can mark one otherwise.
No row is deleted; IDs, statuses, timestamps, projects and schedules are untouched.

On PostgreSQL this is a plain ALTER. On SQLite the CHECK requires a table rebuild, which would
fire the dependents' ON DELETE CASCADE / SET NULL, so their rows are carried through exactly as
migration 0018 does. Down: drops the column and its CHECK.
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

KIND = "task_kind IN ('checklist','board')"
CASCADE_DEPENDENTS = ("task_steps", "daily_priorities")
SET_NULL_DEPENDENTS = (("inbox_items", "converted_task_id"), ("work_sessions", "task_id"))


def kind_column() -> sa.Column:
    return sa.Column("task_kind", sa.String(10), nullable=False, server_default="checklist")


def capture_dependents(bind):
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
            batch.add_column(kind_column())
            batch.create_check_constraint("task_kind", KIND)
        restore_dependents(bind, kept, links)
        return
    op.add_column("tasks", kind_column())
    op.create_check_constraint("task_kind", "tasks", KIND)


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        kept, links = capture_dependents(bind)
        with op.batch_alter_table("tasks") as batch:
            batch.drop_constraint("task_kind", type_="check")
            batch.drop_column("task_kind")
        restore_dependents(bind, kept, links)
        return
    op.drop_constraint("task_kind", "tasks", type_="check")
    op.drop_column("tasks", "task_kind")
