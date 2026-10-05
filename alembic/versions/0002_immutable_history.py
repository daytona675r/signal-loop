"""Protect historical snapshots from accidental SQL/ORM updates and deletes.

Revision ID: 0002
Revises: c3cba3b019c6
"""

from alembic import op

revision = "0002"
down_revision = "c3cba3b019c6"
branch_labels = None
depends_on = None

# No business workflow or LLM logic in these triggers, only append-only protection.
TABLES = (
    "hypothesis_version",
    "transition_history",
    "decision_log",
    "decision_evidence",
    "decision_signal",
    "human_review",
    "source",
    "evidence",
    "signal",
)


def upgrade():
    op.execute("""
        CREATE FUNCTION reject_historical_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only; create a new record instead', TG_TABLE_NAME
                USING ERRCODE = '23514';
        END;
        $$
    """)
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_historical_mutation()"
        )


def downgrade():
    for table in TABLES:
        op.execute(f"DROP TRIGGER immutable_record ON {table}")
    op.execute("DROP FUNCTION reject_historical_mutation()")
