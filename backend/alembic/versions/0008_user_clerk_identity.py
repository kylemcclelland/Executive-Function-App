"""Link users to Clerk accounts.

Purely additive: one nullable column and a unique index; no existing row is changed. The
pre-authentication user keeps a NULL ``clerk_user_id``, so its data stays unreachable to every
Clerk account until it is deliberately claimed (see docs/clerk-data-migration-plan.md).
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("clerk_user_id", sa.String(255), nullable=True))
    op.create_index("uq_users_clerk_user_id", "users", ["clerk_user_id"], unique=True)


def downgrade():
    op.drop_index("uq_users_clerk_user_id", table_name="users")
    op.drop_column("users", "clerk_user_id")
