"""Link research runs relationally to the immutable version under research."""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_run", sa.Column("hypothesis_version_id", sa.UUID(), nullable=True))
    op.create_index("ix_agent_run_hypothesis_version_id", "agent_run", ["hypothesis_version_id"])
    op.create_foreign_key(
        "fk_agent_run_hypothesis_version",
        "agent_run",
        "hypothesis_version",
        ["hypothesis_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade():
    op.drop_constraint("fk_agent_run_hypothesis_version", "agent_run", type_="foreignkey")
    op.drop_index("ix_agent_run_hypothesis_version_id", table_name="agent_run")
    op.drop_column("agent_run", "hypothesis_version_id")
