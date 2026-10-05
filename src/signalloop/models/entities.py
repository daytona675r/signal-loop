import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from signalloop.domain.states import (
    ActorType,
    Decision,
    ExperimentStatus,
    ReviewDecision,
    RunStatus,
    Stance,
    State,
)


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def enum_type(cls, name=None):
    return Enum(
        cls,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda values: [v.value for v in values],
        name=name or cls.__name__.lower(),
    )


def fk(target, **kwargs):
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete="RESTRICT"), index=True, **kwargs
    )


class Identity:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Provenance:
    created_by_type: Mapped[ActorType] = mapped_column(
        enum_type(ActorType), default=ActorType.human
    )
    created_by: Mapped[str] = mapped_column(String(200), default="manual")
    agent_run_id: Mapped[uuid.UUID | None] = fk("agent_run.id")


class Hypothesis(Identity, Provenance, Base):
    __tablename__ = "hypothesis"
    title: Mapped[str] = mapped_column(String(300))
    domain: Mapped[str] = mapped_column(String(200), index=True)
    status: Mapped[State] = mapped_column(enum_type(State), default=State.DRAFT, index=True)
    current_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "current_version_id"],
            ["hypothesis_version.hypothesis_id", "hypothesis_version.id"],
            name="fk_hypothesis_current_version",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
    )


class HypothesisVersion(Identity, Provenance, Base):
    __tablename__ = "hypothesis_version"
    hypothesis_id: Mapped[uuid.UUID] = fk("hypothesis.id")
    version_no: Mapped[int]
    target_customer: Mapped[str] = mapped_column(Text)
    problem: Mapped[str] = mapped_column(Text)
    offer: Mapped[str] = mapped_column(Text)
    price_assumption: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    success_criteria: Mapped[str] = mapped_column(Text)
    change_reason: Mapped[str] = mapped_column(Text)
    originating_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), index=True
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ["hypothesis_id", "originating_decision_id"],
            ["decision_log.hypothesis_id", "decision_log.id"],
            name="fk_version_originating_decision",
            use_alter=True,
        ),
        UniqueConstraint("hypothesis_id", "version_no", name="uq_version_number"),
        UniqueConstraint("hypothesis_id", "id"),
        CheckConstraint("version_no > 0", name="positive_version"),
        CheckConstraint("price_assumption >= 0", name="nonnegative_price"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_code"),
    )


class AgentRun(Identity, Base):
    __tablename__ = "agent_run"
    agent_role: Mapped[str] = mapped_column(String(200))
    run_type: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(200))
    input_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    model: Mapped[str | None] = mapped_column(String(200))
    provider: Mapped[str | None] = mapped_column(String(200))
    trace_id: Mapped[str | None] = mapped_column(String(300), index=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    cost_currency: Mapped[str] = mapped_column(String(3), default="USD")
    latency_ms: Mapped[int | None]
    status: Mapped[RunStatus] = mapped_column(enum_type(RunStatus), default=RunStatus.pending)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("cost >= 0", name="nonnegative_cost"),
        CheckConstraint("latency_ms >= 0", name="nonnegative_latency"),
        CheckConstraint("finished_at >= started_at", name="ordered_times"),
    )


class Source(Identity, Provenance, Base):
    __tablename__ = "source"
    url: Mapped[str | None] = mapped_column(Text)
    platform: Mapped[str | None] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str | None] = mapped_column(String(300))
    external_id: Mapped[str | None] = mapped_column(String(300))
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    source_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)


class Evidence(Identity, Provenance, Base):
    __tablename__ = "evidence"
    source_id: Mapped[uuid.UUID | None] = fk("source.id")
    hypothesis_version_id: Mapped[uuid.UUID] = fk("hypothesis_version.id")
    stance: Mapped[Stance] = mapped_column(enum_type(Stance), default=Stance.unknown)
    strength: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    quote_or_summary: Mapped[str] = mapped_column(Text)
    structured_facts: Mapped[dict] = mapped_column(JSONB, default=dict)
    __table_args__ = (CheckConstraint("strength BETWEEN 0 AND 1", name="strength_range"),)


class Experiment(Identity, Provenance, Base):
    __tablename__ = "experiment"
    hypothesis_version_id: Mapped[uuid.UUID] = fk("hypothesis_version.id")
    name: Mapped[str] = mapped_column(String(300))
    objective: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(200))
    offer_variant: Mapped[str | None] = mapped_column(Text)
    price_test: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    success_criteria: Mapped[str] = mapped_column(Text)
    status: Mapped[ExperimentStatus] = mapped_column(
        enum_type(ExperimentStatus), default=ExperimentStatus.planned
    )
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_summary: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("price_test >= 0", name="nonnegative_price"),
        CheckConstraint("end_at >= start_at", name="ordered_times"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_code"),
    )


class Signal(Identity, Provenance, Base):
    __tablename__ = "signal"
    experiment_id: Mapped[uuid.UUID] = fk("experiment.id")
    signal_type: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    strength: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observation: Mapped[str] = mapped_column(Text)
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    __table_args__ = (CheckConstraint("strength BETWEEN 0 AND 1", name="strength_range"),)


class DecisionLog(Identity, Provenance, Base):
    __tablename__ = "decision_log"
    hypothesis_id: Mapped[uuid.UUID] = fk("hypothesis.id")
    from_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    to_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    decision: Mapped[Decision] = mapped_column(enum_type(Decision))
    rationale: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        ForeignKeyConstraint(
            ["hypothesis_id", "from_version_id"],
            ["hypothesis_version.hypothesis_id", "hypothesis_version.id"],
            name="fk_decision_from_version",
        ),
        ForeignKeyConstraint(
            ["hypothesis_id", "to_version_id"],
            ["hypothesis_version.hypothesis_id", "hypothesis_version.id"],
            name="fk_decision_to_version",
        ),
        UniqueConstraint("hypothesis_id", "id"),
    )


class TransitionHistory(Identity, Provenance, Base):
    __tablename__ = "transition_history"
    hypothesis_id: Mapped[uuid.UUID] = fk("hypothesis.id")
    hypothesis_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    from_state: Mapped[State | None] = mapped_column(enum_type(State, "from_state"))
    to_state: Mapped[State] = mapped_column(enum_type(State, "to_state"))
    reason: Mapped[str] = mapped_column(Text)
    decision_id: Mapped[uuid.UUID | None] = fk("decision_log.id")
    __table_args__ = (
        ForeignKeyConstraint(
            ["hypothesis_id", "hypothesis_version_id"],
            ["hypothesis_version.hypothesis_id", "hypothesis_version.id"],
            name="fk_history_version",
        ),
    )


class DecisionEvidence(Base):
    __tablename__ = "decision_evidence"
    decision_id: Mapped[uuid.UUID] = fk("decision_log.id", primary_key=True)
    evidence_id: Mapped[uuid.UUID] = fk("evidence.id", primary_key=True)


class DecisionSignal(Base):
    __tablename__ = "decision_signal"
    decision_id: Mapped[uuid.UUID] = fk("decision_log.id", primary_key=True)
    signal_id: Mapped[uuid.UUID] = fk("signal.id", primary_key=True)


class HumanReview(Identity, Base):
    __tablename__ = "human_review"
    hypothesis_version_id: Mapped[uuid.UUID | None] = fk("hypothesis_version.id")
    experiment_id: Mapped[uuid.UUID | None] = fk("experiment.id")
    decision_id: Mapped[uuid.UUID | None] = fk("decision_log.id")
    agent_run_id: Mapped[uuid.UUID | None] = fk("agent_run.id")
    decision: Mapped[ReviewDecision] = mapped_column(enum_type(ReviewDecision))
    notes: Mapped[str] = mapped_column(Text)
    reviewed_by: Mapped[str] = mapped_column(String(200))
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(hypothesis_version_id, experiment_id, decision_id, agent_run_id) = 1",
            name="exactly_one_target",
        ),
    )
