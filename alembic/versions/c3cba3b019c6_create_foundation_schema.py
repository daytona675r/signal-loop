"""create foundation schema

Revision ID: c3cba3b019c6
Revises:
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "c3cba3b019c6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_run",
        sa.Column("agent_role", sa.String(length=200), nullable=False),
        sa.Column("run_type", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=200), nullable=True),
        sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("provider", sa.String(length=200), nullable=True),
        sa.Column("trace_id", sa.String(length=300), nullable=True),
        sa.Column("cost", sa.Numeric(precision=14, scale=6), nullable=True),
        sa.Column("cost_currency", sa.String(length=3), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "succeeded",
                "failed",
                name="runstatus",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("cost >= 0", name=op.f("ck_agent_run_nonnegative_cost")),
        sa.CheckConstraint("finished_at >= started_at", name=op.f("ck_agent_run_ordered_times")),
        sa.CheckConstraint("latency_ms >= 0", name=op.f("ck_agent_run_nonnegative_latency")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_run")),
    )
    op.create_index(op.f("ix_agent_run_trace_id"), "agent_run", ["trace_id"], unique=False)
    op.create_table(
        "decision_log",
        sa.Column("hypothesis_id", sa.UUID(), nullable=False),
        sa.Column("from_version_id", sa.UUID(), nullable=False),
        sa.Column("to_version_id", sa.UUID(), nullable=True),
        sa.Column(
            "decision",
            sa.Enum(
                "continue",
                "iterate",
                "pause",
                "reject",
                "validate",
                name="decision",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_by_type",
            sa.Enum(
                "human",
                "agent",
                "system",
                name="actortype",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("agent_run_id", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decision_log")),
        sa.UniqueConstraint("hypothesis_id", "id", name=op.f("uq_decision_log_hypothesis_id")),
    )
    op.create_index(
        op.f("ix_decision_log_agent_run_id"), "decision_log", ["agent_run_id"], unique=False
    )
    op.create_index(
        op.f("ix_decision_log_from_version_id"), "decision_log", ["from_version_id"], unique=False
    )
    op.create_index(
        op.f("ix_decision_log_hypothesis_id"), "decision_log", ["hypothesis_id"], unique=False
    )
    op.create_index(
        op.f("ix_decision_log_to_version_id"), "decision_log", ["to_version_id"], unique=False
    )
    op.create_table(
        "hypothesis_version",
        sa.Column("hypothesis_id", sa.UUID(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("target_customer", sa.Text(), nullable=False),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.Column("offer", sa.Text(), nullable=False),
        sa.Column("price_assumption", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("success_criteria", sa.Text(), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("originating_decision_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_by_type",
            sa.Enum(
                "human",
                "agent",
                "system",
                name="actortype",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("agent_run_id", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name=op.f("ck_hypothesis_version_currency_code")
        ),
        sa.CheckConstraint(
            "price_assumption >= 0", name=op.f("ck_hypothesis_version_nonnegative_price")
        ),
        sa.CheckConstraint("version_no > 0", name=op.f("ck_hypothesis_version_positive_version")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hypothesis_version")),
        sa.UniqueConstraint(
            "hypothesis_id", "id", name=op.f("uq_hypothesis_version_hypothesis_id")
        ),
        sa.UniqueConstraint("hypothesis_id", "version_no", name="uq_version_number"),
    )
    op.create_index(
        op.f("ix_hypothesis_version_agent_run_id"),
        "hypothesis_version",
        ["agent_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_hypothesis_version_hypothesis_id"),
        "hypothesis_version",
        ["hypothesis_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_hypothesis_version_originating_decision_id"),
        "hypothesis_version",
        ["originating_decision_id"],
        unique=False,
    )
    op.create_table(
        "experiment",
        sa.Column("hypothesis_version_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("channel", sa.String(length=200), nullable=False),
        sa.Column("offer_variant", sa.Text(), nullable=True),
        sa.Column("price_test", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("success_criteria", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "planned",
                "running",
                "completed",
                "cancelled",
                name="experimentstatus",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_by_type",
            sa.Enum(
                "human",
                "agent",
                "system",
                name="actortype",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("agent_run_id", sa.UUID(), nullable=True),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_experiment_currency_code")),
        sa.CheckConstraint("end_at >= start_at", name=op.f("ck_experiment_ordered_times")),
        sa.CheckConstraint("price_test >= 0", name=op.f("ck_experiment_nonnegative_price")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiment")),
    )
    op.create_index(
        op.f("ix_experiment_agent_run_id"), "experiment", ["agent_run_id"], unique=False
    )
    op.create_index(
        op.f("ix_experiment_hypothesis_version_id"),
        "experiment",
        ["hypothesis_version_id"],
        unique=False,
    )
    op.create_table(
        "hypothesis",
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("domain", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "FEASIBILITY",
                "RESEARCH",
                "READY_FOR_EXPERIMENT",
                "EXPERIMENT",
                "EVALUATION",
                "ITERATION",
                "PAUSED",
                "REJECTED",
                "VALIDATED",
                name="state",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("current_version_id", sa.UUID(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_by_type",
            sa.Enum(
                "human",
                "agent",
                "system",
                name="actortype",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("agent_run_id", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hypothesis")),
    )
    op.create_index(
        op.f("ix_hypothesis_agent_run_id"), "hypothesis", ["agent_run_id"], unique=False
    )
    op.create_index(op.f("ix_hypothesis_domain"), "hypothesis", ["domain"], unique=False)
    op.create_index(op.f("ix_hypothesis_status"), "hypothesis", ["status"], unique=False)
    op.create_table(
        "source",
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("platform", sa.String(length=200), nullable=True),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("external_id", sa.String(length=300), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_hash", sa.String(length=128), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_by_type",
            sa.Enum(
                "human",
                "agent",
                "system",
                name="actortype",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("agent_run_id", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source")),
    )
    op.create_index(op.f("ix_source_agent_run_id"), "source", ["agent_run_id"], unique=False)
    op.create_index(op.f("ix_source_source_hash"), "source", ["source_hash"], unique=False)
    op.create_index(op.f("ix_source_source_type"), "source", ["source_type"], unique=False)
    op.create_table(
        "evidence",
        sa.Column("source_id", sa.UUID(), nullable=True),
        sa.Column("hypothesis_version_id", sa.UUID(), nullable=False),
        sa.Column(
            "stance",
            sa.Enum(
                "supports",
                "contradicts",
                "neutral",
                "unknown",
                name="stance",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("strength", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("quote_or_summary", sa.Text(), nullable=False),
        sa.Column("structured_facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_by_type",
            sa.Enum(
                "human",
                "agent",
                "system",
                name="actortype",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("agent_run_id", sa.UUID(), nullable=True),
        sa.CheckConstraint("strength BETWEEN 0 AND 1", name=op.f("ck_evidence_strength_range")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence")),
    )
    op.create_index(op.f("ix_evidence_agent_run_id"), "evidence", ["agent_run_id"], unique=False)
    op.create_index(
        op.f("ix_evidence_hypothesis_version_id"),
        "evidence",
        ["hypothesis_version_id"],
        unique=False,
    )
    op.create_index(op.f("ix_evidence_source_id"), "evidence", ["source_id"], unique=False)
    op.create_table(
        "human_review",
        sa.Column("hypothesis_version_id", sa.UUID(), nullable=True),
        sa.Column("experiment_id", sa.UUID(), nullable=True),
        sa.Column("decision_id", sa.UUID(), nullable=True),
        sa.Column("agent_run_id", sa.UUID(), nullable=True),
        sa.Column(
            "decision",
            sa.Enum(
                "approved",
                "rejected",
                "modified",
                "escalated",
                name="reviewdecision",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.String(length=200), nullable=False),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "num_nonnulls(hypothesis_version_id, experiment_id, decision_id, agent_run_id) = 1",
            name=op.f("ck_human_review_exactly_one_target"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_human_review")),
    )
    op.create_index(
        op.f("ix_human_review_agent_run_id"), "human_review", ["agent_run_id"], unique=False
    )
    op.create_index(
        op.f("ix_human_review_decision_id"), "human_review", ["decision_id"], unique=False
    )
    op.create_index(
        op.f("ix_human_review_experiment_id"), "human_review", ["experiment_id"], unique=False
    )
    op.create_index(
        op.f("ix_human_review_hypothesis_version_id"),
        "human_review",
        ["hypothesis_version_id"],
        unique=False,
    )
    op.create_table(
        "signal",
        sa.Column("experiment_id", sa.UUID(), nullable=False),
        sa.Column("signal_type", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("strength", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observation", sa.Text(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_by_type",
            sa.Enum(
                "human",
                "agent",
                "system",
                name="actortype",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("agent_run_id", sa.UUID(), nullable=True),
        sa.CheckConstraint("strength BETWEEN 0 AND 1", name=op.f("ck_signal_strength_range")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signal")),
    )
    op.create_index(op.f("ix_signal_agent_run_id"), "signal", ["agent_run_id"], unique=False)
    op.create_index(op.f("ix_signal_experiment_id"), "signal", ["experiment_id"], unique=False)
    op.create_index(op.f("ix_signal_signal_type"), "signal", ["signal_type"], unique=False)
    op.create_table(
        "transition_history",
        sa.Column("hypothesis_id", sa.UUID(), nullable=False),
        sa.Column("hypothesis_version_id", sa.UUID(), nullable=False),
        sa.Column(
            "from_state",
            sa.Enum(
                "DRAFT",
                "FEASIBILITY",
                "RESEARCH",
                "READY_FOR_EXPERIMENT",
                "EXPERIMENT",
                "EVALUATION",
                "ITERATION",
                "PAUSED",
                "REJECTED",
                "VALIDATED",
                name="from_state",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "to_state",
            sa.Enum(
                "DRAFT",
                "FEASIBILITY",
                "RESEARCH",
                "READY_FOR_EXPERIMENT",
                "EXPERIMENT",
                "EVALUATION",
                "ITERATION",
                "PAUSED",
                "REJECTED",
                "VALIDATED",
                name="to_state",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_by_type",
            sa.Enum(
                "human",
                "agent",
                "system",
                name="actortype",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("agent_run_id", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transition_history")),
    )
    op.create_index(
        op.f("ix_transition_history_agent_run_id"),
        "transition_history",
        ["agent_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transition_history_decision_id"),
        "transition_history",
        ["decision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transition_history_hypothesis_id"),
        "transition_history",
        ["hypothesis_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transition_history_hypothesis_version_id"),
        "transition_history",
        ["hypothesis_version_id"],
        unique=False,
    )
    op.create_table(
        "decision_evidence",
        sa.Column("decision_id", sa.UUID(), nullable=False),
        sa.Column("evidence_id", sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint("decision_id", "evidence_id", name=op.f("pk_decision_evidence")),
    )
    op.create_index(
        op.f("ix_decision_evidence_decision_id"), "decision_evidence", ["decision_id"], unique=False
    )
    op.create_index(
        op.f("ix_decision_evidence_evidence_id"), "decision_evidence", ["evidence_id"], unique=False
    )
    op.create_table(
        "decision_signal",
        sa.Column("decision_id", sa.UUID(), nullable=False),
        sa.Column("signal_id", sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint("decision_id", "signal_id", name=op.f("pk_decision_signal")),
    )
    op.create_index(
        op.f("ix_decision_signal_decision_id"), "decision_signal", ["decision_id"], unique=False
    )
    op.create_index(
        op.f("ix_decision_signal_signal_id"), "decision_signal", ["signal_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_decision_log_agent_run_id_agent_run"),
        "decision_log",
        "agent_run",
        ["agent_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_decision_from_version",
        "decision_log",
        "hypothesis_version",
        ["hypothesis_id", "from_version_id"],
        ["hypothesis_id", "id"],
    )
    op.create_foreign_key(
        "fk_decision_to_version",
        "decision_log",
        "hypothesis_version",
        ["hypothesis_id", "to_version_id"],
        ["hypothesis_id", "id"],
    )
    op.create_foreign_key(
        op.f("fk_decision_log_hypothesis_id_hypothesis"),
        "decision_log",
        "hypothesis",
        ["hypothesis_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_hypothesis_version_agent_run_id_agent_run"),
        "hypothesis_version",
        "agent_run",
        ["agent_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_hypothesis_version_hypothesis_id_hypothesis"),
        "hypothesis_version",
        "hypothesis",
        ["hypothesis_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_experiment_agent_run_id_agent_run"),
        "experiment",
        "agent_run",
        ["agent_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_experiment_hypothesis_version_id_hypothesis_version"),
        "experiment",
        "hypothesis_version",
        ["hypothesis_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_hypothesis_agent_run_id_agent_run"),
        "hypothesis",
        "agent_run",
        ["agent_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_hypothesis_current_version",
        "hypothesis",
        "hypothesis_version",
        ["id", "current_version_id"],
        ["hypothesis_id", "id"],
        initially="DEFERRED",
        deferrable=True,
    )
    op.create_foreign_key(
        op.f("fk_source_agent_run_id_agent_run"),
        "source",
        "agent_run",
        ["agent_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_evidence_agent_run_id_agent_run"),
        "evidence",
        "agent_run",
        ["agent_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_evidence_hypothesis_version_id_hypothesis_version"),
        "evidence",
        "hypothesis_version",
        ["hypothesis_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_evidence_source_id_source"),
        "evidence",
        "source",
        ["source_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_human_review_agent_run_id_agent_run"),
        "human_review",
        "agent_run",
        ["agent_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_human_review_decision_id_decision_log"),
        "human_review",
        "decision_log",
        ["decision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_human_review_experiment_id_experiment"),
        "human_review",
        "experiment",
        ["experiment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_human_review_hypothesis_version_id_hypothesis_version"),
        "human_review",
        "hypothesis_version",
        ["hypothesis_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_signal_agent_run_id_agent_run"),
        "signal",
        "agent_run",
        ["agent_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_signal_experiment_id_experiment"),
        "signal",
        "experiment",
        ["experiment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_transition_history_agent_run_id_agent_run"),
        "transition_history",
        "agent_run",
        ["agent_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_transition_history_decision_id_decision_log"),
        "transition_history",
        "decision_log",
        ["decision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_history_version",
        "transition_history",
        "hypothesis_version",
        ["hypothesis_id", "hypothesis_version_id"],
        ["hypothesis_id", "id"],
    )
    op.create_foreign_key(
        op.f("fk_transition_history_hypothesis_id_hypothesis"),
        "transition_history",
        "hypothesis",
        ["hypothesis_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_decision_evidence_decision_id_decision_log"),
        "decision_evidence",
        "decision_log",
        ["decision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_decision_evidence_evidence_id_evidence"),
        "decision_evidence",
        "evidence",
        ["evidence_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_decision_signal_decision_id_decision_log"),
        "decision_signal",
        "decision_log",
        ["decision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_decision_signal_signal_id_signal"),
        "decision_signal",
        "signal",
        ["signal_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_version_originating_decision",
        "hypothesis_version",
        "decision_log",
        ["hypothesis_id", "originating_decision_id"],
        ["hypothesis_id", "id"],
    )


def downgrade():
    op.drop_constraint("fk_version_originating_decision", "hypothesis_version", type_="foreignkey")
    op.drop_constraint(
        op.f("fk_decision_log_agent_run_id_agent_run"), "decision_log", type_="foreignkey"
    )
    op.drop_constraint("fk_decision_from_version", "decision_log", type_="foreignkey")
    op.drop_constraint("fk_decision_to_version", "decision_log", type_="foreignkey")
    op.drop_constraint(
        op.f("fk_decision_log_hypothesis_id_hypothesis"), "decision_log", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_hypothesis_version_agent_run_id_agent_run"),
        "hypothesis_version",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_hypothesis_version_hypothesis_id_hypothesis"),
        "hypothesis_version",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_experiment_agent_run_id_agent_run"), "experiment", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_experiment_hypothesis_version_id_hypothesis_version"),
        "experiment",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_hypothesis_agent_run_id_agent_run"), "hypothesis", type_="foreignkey"
    )
    op.drop_constraint("fk_hypothesis_current_version", "hypothesis", type_="foreignkey")
    op.drop_constraint(op.f("fk_source_agent_run_id_agent_run"), "source", type_="foreignkey")
    op.drop_constraint(op.f("fk_evidence_agent_run_id_agent_run"), "evidence", type_="foreignkey")
    op.drop_constraint(
        op.f("fk_evidence_hypothesis_version_id_hypothesis_version"), "evidence", type_="foreignkey"
    )
    op.drop_constraint(op.f("fk_evidence_source_id_source"), "evidence", type_="foreignkey")
    op.drop_constraint(
        op.f("fk_human_review_agent_run_id_agent_run"), "human_review", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_human_review_decision_id_decision_log"), "human_review", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_human_review_experiment_id_experiment"), "human_review", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_human_review_hypothesis_version_id_hypothesis_version"),
        "human_review",
        type_="foreignkey",
    )
    op.drop_constraint(op.f("fk_signal_agent_run_id_agent_run"), "signal", type_="foreignkey")
    op.drop_constraint(op.f("fk_signal_experiment_id_experiment"), "signal", type_="foreignkey")
    op.drop_constraint(
        op.f("fk_transition_history_agent_run_id_agent_run"),
        "transition_history",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_transition_history_decision_id_decision_log"),
        "transition_history",
        type_="foreignkey",
    )
    op.drop_constraint("fk_history_version", "transition_history", type_="foreignkey")
    op.drop_constraint(
        op.f("fk_transition_history_hypothesis_id_hypothesis"),
        "transition_history",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_decision_evidence_decision_id_decision_log"),
        "decision_evidence",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_decision_evidence_evidence_id_evidence"), "decision_evidence", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_decision_signal_decision_id_decision_log"), "decision_signal", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_decision_signal_signal_id_signal"), "decision_signal", type_="foreignkey"
    )
    op.drop_index(op.f("ix_decision_signal_signal_id"), table_name="decision_signal")
    op.drop_index(op.f("ix_decision_signal_decision_id"), table_name="decision_signal")
    op.drop_table("decision_signal")
    op.drop_index(op.f("ix_decision_evidence_evidence_id"), table_name="decision_evidence")
    op.drop_index(op.f("ix_decision_evidence_decision_id"), table_name="decision_evidence")
    op.drop_table("decision_evidence")
    op.drop_index(
        op.f("ix_transition_history_hypothesis_version_id"), table_name="transition_history"
    )
    op.drop_index(op.f("ix_transition_history_hypothesis_id"), table_name="transition_history")
    op.drop_index(op.f("ix_transition_history_decision_id"), table_name="transition_history")
    op.drop_index(op.f("ix_transition_history_agent_run_id"), table_name="transition_history")
    op.drop_table("transition_history")
    op.drop_index(op.f("ix_signal_signal_type"), table_name="signal")
    op.drop_index(op.f("ix_signal_experiment_id"), table_name="signal")
    op.drop_index(op.f("ix_signal_agent_run_id"), table_name="signal")
    op.drop_table("signal")
    op.drop_index(op.f("ix_human_review_hypothesis_version_id"), table_name="human_review")
    op.drop_index(op.f("ix_human_review_experiment_id"), table_name="human_review")
    op.drop_index(op.f("ix_human_review_decision_id"), table_name="human_review")
    op.drop_index(op.f("ix_human_review_agent_run_id"), table_name="human_review")
    op.drop_table("human_review")
    op.drop_index(op.f("ix_evidence_source_id"), table_name="evidence")
    op.drop_index(op.f("ix_evidence_hypothesis_version_id"), table_name="evidence")
    op.drop_index(op.f("ix_evidence_agent_run_id"), table_name="evidence")
    op.drop_table("evidence")
    op.drop_index(op.f("ix_source_source_type"), table_name="source")
    op.drop_index(op.f("ix_source_source_hash"), table_name="source")
    op.drop_index(op.f("ix_source_agent_run_id"), table_name="source")
    op.drop_table("source")
    op.drop_index(op.f("ix_hypothesis_status"), table_name="hypothesis")
    op.drop_index(op.f("ix_hypothesis_domain"), table_name="hypothesis")
    op.drop_index(op.f("ix_hypothesis_agent_run_id"), table_name="hypothesis")
    op.drop_table("hypothesis")
    op.drop_index(op.f("ix_experiment_hypothesis_version_id"), table_name="experiment")
    op.drop_index(op.f("ix_experiment_agent_run_id"), table_name="experiment")
    op.drop_table("experiment")
    op.drop_index(
        op.f("ix_hypothesis_version_originating_decision_id"), table_name="hypothesis_version"
    )
    op.drop_index(op.f("ix_hypothesis_version_hypothesis_id"), table_name="hypothesis_version")
    op.drop_index(op.f("ix_hypothesis_version_agent_run_id"), table_name="hypothesis_version")
    op.drop_table("hypothesis_version")
    op.drop_index(op.f("ix_decision_log_to_version_id"), table_name="decision_log")
    op.drop_index(op.f("ix_decision_log_hypothesis_id"), table_name="decision_log")
    op.drop_index(op.f("ix_decision_log_from_version_id"), table_name="decision_log")
    op.drop_index(op.f("ix_decision_log_agent_run_id"), table_name="decision_log")
    op.drop_table("decision_log")
    op.drop_index(op.f("ix_agent_run_trace_id"), table_name="agent_run")
    op.drop_table("agent_run")
