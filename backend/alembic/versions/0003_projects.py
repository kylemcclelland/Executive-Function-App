"""Add projects, milestones, project notes, and progress updates.

Tasks already carried an unconstrained ``project_id``. Any value in use becomes a real
"Untitled project" owned by the task's user, so existing groupings survive.
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('active','paused','someday','completed')", name="project_status",
        ),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])
    op.create_index("ix_projects_user_status", "projects", ["user_id", "status"])
    op.create_table(
        "project_milestones",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_project_milestones_user_id", "project_milestones", ["user_id"])
    op.create_index("ix_milestones_project", "project_milestones", ["project_id", "position"])
    op.create_table(
        "project_notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(300), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_project_notes_user_id", "project_notes", ["user_id"])
    op.create_index("ix_project_notes_project", "project_notes", ["project_id", "updated_at"])
    op.create_table(
        "project_updates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("next_step", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('progress','session')", name="project_update_kind"),
    )
    op.create_index("ix_project_updates_user_id", "project_updates", ["user_id"])
    op.create_index("ix_project_updates_project", "project_updates", ["project_id", "created_at"])

    op.add_column("tasks", sa.Column("milestone_id", sa.Uuid(), nullable=True))
    op.add_column("tasks", sa.Column("project_position", sa.Integer(), nullable=True))
    preserve_existing_project_ids()
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    # SQLite cannot add a constraint to an existing table without rebuilding it, and a
    # rebuild with foreign keys enabled would cascade-delete steps and priorities. The
    # application enforces the same ownership and unlink rules on every dialect.
    if not is_sqlite():
        op.create_foreign_key(
            "fk_tasks_project_id", "tasks", "projects", ["project_id"], ["id"],
            ondelete="SET NULL",
        )
        op.create_foreign_key(
            "fk_tasks_milestone_id", "tasks", "project_milestones", ["milestone_id"], ["id"],
            ondelete="SET NULL",
        )


def preserve_existing_project_ids():
    tasks = sa.table(
        "tasks", sa.column("user_id", sa.Uuid()), sa.column("project_id", sa.Uuid()),
    )
    projects = sa.table(
        "projects", sa.column("id", sa.Uuid()), sa.column("user_id", sa.Uuid()),
        sa.column("name", sa.String()), sa.column("status", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    connection = op.get_bind()
    owners: dict = {}
    for user_id, project_id in connection.execute(
        sa.select(tasks.c.user_id, tasks.c.project_id)
        .where(tasks.c.project_id.is_not(None)).distinct()
    ):
        owners.setdefault(project_id, user_id)
    now = sa.func.now()
    if owners:
        connection.execute(sa.insert(projects).values([
            {"id": project_id, "user_id": user_id, "name": "Untitled project",
             "status": "active", "created_at": now, "updated_at": now}
            for project_id, user_id in owners.items()
        ]))
    # A reused identifier can only belong to one user; never leave a cross-user link.
    connection.execute(
        sa.update(tasks).where(
            tasks.c.project_id.is_not(None),
            ~sa.exists().where(
                projects.c.id == tasks.c.project_id, projects.c.user_id == tasks.c.user_id,
            ),
        ).values(project_id=None)
    )


def downgrade():
    if not is_sqlite():
        op.drop_constraint("fk_tasks_milestone_id", "tasks", type_="foreignkey")
        op.drop_constraint("fk_tasks_project_id", "tasks", type_="foreignkey")
    op.drop_index("ix_tasks_project_id", table_name="tasks")
    for column in ("project_position", "milestone_id"):
        if is_sqlite():
            op.execute(f"ALTER TABLE tasks DROP COLUMN {column}")
        else:
            op.drop_column("tasks", column)
    for table in ("project_updates", "project_notes", "project_milestones", "projects"):
        op.drop_table(table)
