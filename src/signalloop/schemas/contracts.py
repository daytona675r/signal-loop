from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic.types import AwareDatetime

from signalloop.domain.states import (
    ActorType,
    Decision,
    ExperimentStatus,
    ReviewDecision,
    RunStatus,
    Stance,
    State,
)

Text = Annotated[str, Field(min_length=1, max_length=20000)]
Short = Annotated[str, Field(min_length=1, max_length=200)]
Title = Annotated[str, Field(min_length=1, max_length=300)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Strength = Annotated[Decimal, Field(ge=0, le=1, max_digits=4, decimal_places=3)]


def now():
    return datetime.now(UTC)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, from_attributes=True)


class Provenance(Contract):
    created_by_type: ActorType = ActorType.human
    created_by: Short = "manual"
    agent_run_id: UUID | None = None


class VersionFields(Provenance):
    target_customer: Text
    problem: Text
    offer: Text
    price_assumption: Money | None = None
    currency: Currency = "EUR"
    success_criteria: Text
    change_reason: Text


class HypothesisCreate(Provenance):
    title: Title
    domain: Short
    version: VersionFields


class VersionCreate(VersionFields):
    originating_decision_id: UUID | None = None


class Record(Contract):
    id: UUID
    created_at: AwareDatetime


class HypothesisRead(Record, Provenance):
    title: str
    domain: str
    status: State
    current_version_id: UUID
    updated_at: AwareDatetime


class VersionRead(Record, VersionCreate):
    hypothesis_id: UUID
    version_no: int


class TransitionCreate(Provenance):
    target_state: State
    reason: Text


class HistoryRead(Record, Provenance):
    hypothesis_id: UUID
    hypothesis_version_id: UUID
    from_state: State | None
    to_state: State
    reason: str
    decision_id: UUID | None


class SourceCreate(Provenance):
    url: str | None = None
    platform: Short | None = None
    source_type: Annotated[str, Field(min_length=1, max_length=100)]
    title: Title | None = None
    external_id: Title | None = None
    captured_at: AwareDatetime = Field(default_factory=now)
    source_hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    metadata: dict = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def http_url(cls, value):
        return str(HttpUrl(value)) if value is not None else None


class SourceRead(Record, SourceCreate):
    metadata: dict = Field(validation_alias="metadata_", serialization_alias="metadata")


class EvidenceCreate(Provenance):
    hypothesis_version_id: UUID | None = None
    source_id: UUID | None = None
    stance: Stance = Stance.unknown
    strength: Strength | None = None
    quote_or_summary: Text
    structured_facts: dict = Field(default_factory=dict)


class EvidenceRead(Record, EvidenceCreate):
    hypothesis_version_id: UUID


class ExperimentCreate(Provenance):
    hypothesis_version_id: UUID | None = None
    name: Title
    objective: Text
    channel: Short
    offer_variant: Text | None = None
    price_test: Money | None = None
    currency: Currency = "EUR"
    success_criteria: Text
    status: ExperimentStatus = ExperimentStatus.planned
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    result_summary: Text | None = None

    @field_validator("end_at")
    @classmethod
    def ordered_times(cls, value, info: ValidationInfo):
        start = info.data.get("start_at")
        if value is not None and start is not None and value < start:
            raise ValueError("end_at must not precede start_at")
        return value


class ExperimentRead(Record, ExperimentCreate):
    hypothesis_version_id: UUID


class SignalCreate(Provenance):
    signal_type: Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")]
    value: Annotated[Decimal, Field(max_digits=18, decimal_places=6)] | None = None
    strength: Strength | None = None
    occurred_at: AwareDatetime
    observation: Text = Field(
        description="Observed event or feedback; never an LLM interpretation."
    )
    raw_payload: dict = Field(default_factory=dict)


class SignalRead(Record, SignalCreate):
    experiment_id: UUID


class DecisionCreate(Provenance):
    from_version_id: UUID | None = None
    to_version_id: UUID | None = None
    decision: Decision
    rationale: Text
    supporting_evidence_ids: list[UUID] = Field(default_factory=list, max_length=100)
    supporting_signal_ids: list[UUID] = Field(default_factory=list, max_length=100)


class DecisionRead(Record, DecisionCreate):
    hypothesis_id: UUID
    from_version_id: UUID
    resulting_version_ids: list[UUID] = Field(default_factory=list)


class AgentRunCreate(Contract):
    agent_role: Short
    run_type: Annotated[str, Field(min_length=1, max_length=100)]
    prompt_version: Short | None = None
    input_snapshot: dict = Field(default_factory=dict)
    output_snapshot: dict = Field(default_factory=dict)
    model: Short | None = None
    provider: Short | None = None
    trace_id: Title | None = None
    cost: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=6)] | None = None
    cost_currency: Currency = "USD"
    latency_ms: Annotated[int, Field(ge=0, le=2147483647)] | None = None
    status: RunStatus = RunStatus.pending
    error: Text | None = None
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None

    @field_validator("finished_at")
    @classmethod
    def ordered_times(cls, value, info):
        start = info.data.get("started_at")
        if value is not None and start is not None and value < start:
            raise ValueError("finished_at must not precede started_at")
        return value


class AgentRunRead(Record, AgentRunCreate):
    pass


class HumanReviewCreate(Contract):
    hypothesis_version_id: UUID | None = None
    experiment_id: UUID | None = None
    decision_id: UUID | None = None
    agent_run_id: UUID | None = None
    decision: ReviewDecision
    notes: Text
    reviewed_by: Short
    reviewed_at: AwareDatetime = Field(default_factory=now)

    @model_validator(mode="after")
    def one_target(self):
        targets = [
            self.hypothesis_version_id,
            self.experiment_id,
            self.decision_id,
            self.agent_run_id,
        ]
        if sum(target is not None for target in targets) != 1:
            raise ValueError("Exactly one review target is required")
        return self


class HumanReviewRead(Record, HumanReviewCreate):
    pass


class HealthRead(Contract):
    status: Literal["ok"]
