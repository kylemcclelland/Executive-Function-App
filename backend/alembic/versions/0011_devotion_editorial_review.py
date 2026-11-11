"""Devotions, editorial review: richer source metadata, a "restricted" rights status, grouped steps.

* prayer_texts: the issuing authority, the publication date, and when the wording was copied; a text
  may hold NO wording while it is only a proposal (citation and link recorded, wording withheld
  because its rights are not cleared). Everything past "proposed" still needs wording, a cited
  source and cleared rights, enforced by CHECK constraints as before.
* devotions: a label for the choice when steps are grouped (the Rosary's mysteries) and where the
  explanatory prose came from.

Additive, apart from the two replaced CHECK constraints (relaxed only for "proposed", tightened for
"restricted" rights). No row is changed and no devotion or prayer text is inserted.
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def quoted(*values: str) -> str:
    return ",".join(f"'{value}'" for value in values)


# Frozen here on purpose: a migration must keep meaning what it meant when it was written.
LICENSES_NEW = quoted("unverified", "restricted", "public_domain", "licensed", "permission_granted")
LICENSES_OLD = quoted("unverified", "public_domain", "licensed", "permission_granted")


def upgrade():
    with op.batch_alter_table("devotions") as batch:
        batch.add_column(sa.Column("choice_label", sa.String(60), nullable=True))
        batch.add_column(sa.Column("prose_origin", sa.String(40), nullable=True))
    with op.batch_alter_table("prayer_texts") as batch:
        batch.add_column(sa.Column("source_authority", sa.String(500), nullable=True))
        batch.add_column(sa.Column("source_date", sa.String(100), nullable=True))
        batch.add_column(
            sa.Column("source_retrieved_at", sa.DateTime(timezone=True), nullable=True),
        )
        batch.drop_constraint("prayer_text_license", type_="check")
        batch.drop_constraint("prayer_text_body", type_="check")
        batch.drop_constraint("prayer_text_source_recorded", type_="check")
        batch.create_check_constraint("prayer_text_license", f"license_status IN ({LICENSES_NEW})")
        batch.create_check_constraint(
            "prayer_text_body", "status = 'proposed' OR length(trim(body)) > 0",
        )
        batch.create_check_constraint(
            "prayer_text_source_recorded",
            "status = 'proposed' OR (source_title IS NOT NULL AND attribution IS NOT NULL "
            "AND license_status NOT IN ('unverified','restricted') "
            "AND source_verified_by IS NOT NULL AND source_verified_at IS NOT NULL)",
        )


def downgrade():
    # The older schema cannot hold these rows: a text with no wording, or "restricted" rights.
    op.execute("DELETE FROM devotion_events WHERE text_id IN "
               "(SELECT id FROM prayer_texts WHERE length(trim(body)) = 0)")
    op.execute("DELETE FROM prayer_texts WHERE length(trim(body)) = 0")
    op.execute(
        "UPDATE prayer_texts SET license_status = 'unverified' WHERE license_status = 'restricted'"
    )
    with op.batch_alter_table("prayer_texts") as batch:
        batch.drop_constraint("prayer_text_source_recorded", type_="check")
        batch.drop_constraint("prayer_text_body", type_="check")
        batch.drop_constraint("prayer_text_license", type_="check")
        batch.create_check_constraint("prayer_text_license", f"license_status IN ({LICENSES_OLD})")
        batch.create_check_constraint("prayer_text_body", "length(trim(body)) > 0")
        batch.create_check_constraint(
            "prayer_text_source_recorded",
            "status = 'proposed' OR (source_title IS NOT NULL AND attribution IS NOT NULL "
            "AND license_status <> 'unverified' AND source_verified_by IS NOT NULL "
            "AND source_verified_at IS NOT NULL)",
        )
        batch.drop_column("source_retrieved_at")
        batch.drop_column("source_date")
        batch.drop_column("source_authority")
    with op.batch_alter_table("devotions") as batch:
        batch.drop_column("prose_origin")
        batch.drop_column("choice_label")
