"""Order transition history independently of timestamps and transaction timing.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("transition_history", sa.Column("sequence_no", sa.Integer(), nullable=True))
    # Only backfill the new ordering field; do not change historical facts.
    op.execute("ALTER TABLE transition_history DISABLE TRIGGER immutable_record")
    op.execute("""
        UPDATE transition_history AS history SET sequence_no = numbered.sequence_no
        FROM (
            SELECT id, row_number() OVER (
                PARTITION BY hypothesis_id ORDER BY created_at, id
            ) AS sequence_no FROM transition_history
        ) AS numbered WHERE history.id = numbered.id
    """)
    op.execute("ALTER TABLE transition_history ENABLE TRIGGER immutable_record")
    op.alter_column("transition_history", "sequence_no", nullable=False)
    op.create_unique_constraint(
        "uq_history_sequence", "transition_history", ["hypothesis_id", "sequence_no"]
    )
    op.create_check_constraint("positive_sequence", "transition_history", "sequence_no > 0")


def downgrade():
    op.drop_constraint(
        op.f("ck_transition_history_positive_sequence"), "transition_history", type_="check"
    )
    op.drop_constraint("uq_history_sequence", "transition_history", type_="unique")
    op.drop_column("transition_history", "sequence_no")
