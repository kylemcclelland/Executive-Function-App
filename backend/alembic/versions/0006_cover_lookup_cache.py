"""Cache Open Library cover lookups and remember rate-limit cooldowns.

Purely additive: two new tables; no existing table or row is changed.
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cover_lookups",
        sa.Column("isbn", sa.String(13), primary_key=True),
        sa.Column("result", sa.String(12), nullable=False),
        sa.Column("looked_up_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("result IN ('found','not_found')", name="cover_lookup_result"),
    )
    op.create_table(
        "cover_service_state",
        sa.Column("name", sa.String(40), primary_key=True),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("cover_service_state")
    op.drop_table("cover_lookups")
