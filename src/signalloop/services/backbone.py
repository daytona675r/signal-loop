from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from signalloop.domain.states import (
    DECISION_TARGETS,
    Decision,
    DomainError,
    RunStatus,
    State,
    validate_transition,
)
from signalloop.models import entities as m
from signalloop.repositories.store import Store
from signalloop.research.constants import ROLE, RUN_TYPE
from signalloop.schemas import contracts as c


def provenance(payload):
    return {key: getattr(payload, key) for key in ("created_by_type", "created_by", "agent_run_id")}


class Backbone:
    """Deterministic operations. Call inside one transaction (HTTP or a future worker)."""

    def __init__(self, session: Session):
        self.session = session
        self.store = Store(session)

    def check_provenance(self, payload):
        if payload.agent_run_id is not None:
            self.store.require(m.AgentRun, payload.agent_run_id)

    def version_for(self, hypothesis, version_id=None):
        version = self.store.require(
            m.HypothesisVersion, version_id or hypothesis.current_version_id
        )
        if version.hypothesis_id != hypothesis.id:
            raise DomainError("Version belongs to a different hypothesis", 422)
        return version

    def create_hypothesis(self, payload: c.HypothesisCreate):
        self.check_provenance(payload)
        self.check_provenance(payload.version)
        version_id = uuid4()
        hypothesis = self.store.add(
            m.Hypothesis(
                id=uuid4(),
                title=payload.title,
                domain=payload.domain,
                current_version_id=version_id,
                **provenance(payload),
            )
        )
        self.store.add(
            m.HypothesisVersion(
                id=version_id,
                hypothesis_id=hypothesis.id,
                version_no=1,
                **payload.version.model_dump(),
            )
        )
        self.store.add(
            m.TransitionHistory(
                hypothesis_id=hypothesis.id,
                hypothesis_version_id=version_id,
                from_state=None,
                to_state=State.DRAFT,
                reason="Hypothesis created",
                sequence_no=1,
                **provenance(payload),
            )
        )
        return hypothesis

    def create_version(self, hypothesis_id, payload: c.VersionCreate):
        hypothesis = self.store.lock_hypothesis(hypothesis_id)
        self.check_provenance(payload)
        current = self.version_for(hypothesis)
        if payload.originating_decision_id:
            decision = self.store.require(m.DecisionLog, payload.originating_decision_id)
            if decision.hypothesis_id != hypothesis.id:
                raise DomainError("Decision belongs to a different hypothesis", 422)
            if decision.decision != Decision.iterate:
                raise DomainError("Originating decision must be an iterate decision", 422)
            if decision.from_version_id != current.id:
                raise DomainError("Originating decision must refer to the current version", 422)
            if hypothesis.status != State.ITERATION:
                raise DomainError("An originating decision requires the ITERATION state", 422)
            latest_transition = self.session.scalar(
                select(m.TransitionHistory)
                .where(m.TransitionHistory.hypothesis_id == hypothesis.id)
                .order_by(m.TransitionHistory.sequence_no.desc())
                .limit(1)
            )
            if latest_transition is None or latest_transition.decision_id != decision.id:
                raise DomainError(
                    "Originating decision must have started the current iteration", 422
                )
        version = self.store.add(
            m.HypothesisVersion(
                hypothesis_id=hypothesis.id,
                version_no=current.version_no + 1,
                **payload.model_dump(),
            )
        )
        hypothesis.current_version_id = version.id
        hypothesis.updated_at = datetime.now(UTC)
        self.session.flush()
        return version

    def versions(self, hypothesis_id, limit=100, offset=0):
        self.store.require(m.Hypothesis, hypothesis_id)
        return list(
            self.session.scalars(
                select(m.HypothesisVersion)
                .where(m.HypothesisVersion.hypothesis_id == hypothesis_id)
                .order_by(m.HypothesisVersion.version_no)
                .limit(limit)
                .offset(offset)
            )
        )

    def get_version(self, hypothesis_id, version_no):
        self.store.require(m.Hypothesis, hypothesis_id)
        version = self.session.scalar(
            select(m.HypothesisVersion).where(
                m.HypothesisVersion.hypothesis_id == hypothesis_id,
                m.HypothesisVersion.version_no == version_no,
            )
        )
        if version is None:
            raise DomainError("HypothesisVersion not found", 404)
        return version

    def _transition(self, hypothesis, target, reason, actor, decision_id=None):
        validate_transition(hypothesis.status, target)
        sequence_no = (
            self.session.scalar(
                select(func.max(m.TransitionHistory.sequence_no)).where(
                    m.TransitionHistory.hypothesis_id == hypothesis.id
                )
            )
            + 1
        )
        previous = hypothesis.status
        hypothesis.status = target
        hypothesis.updated_at = datetime.now(UTC)
        return self.store.add(
            m.TransitionHistory(
                hypothesis_id=hypothesis.id,
                hypothesis_version_id=hypothesis.current_version_id,
                sequence_no=sequence_no,
                from_state=previous,
                to_state=target,
                reason=reason,
                decision_id=decision_id,
                **provenance(actor),
            )
        )

    def transition(self, hypothesis_id, payload: c.TransitionCreate):
        hypothesis = self.store.lock_hypothesis(hypothesis_id)
        self.check_provenance(payload)
        return self._transition(hypothesis, payload.target_state, payload.reason, payload)

    def history(self, hypothesis_id, limit=100, offset=0):
        self.store.require(m.Hypothesis, hypothesis_id)
        return list(
            self.session.scalars(
                select(m.TransitionHistory)
                .where(m.TransitionHistory.hypothesis_id == hypothesis_id)
                .order_by(m.TransitionHistory.sequence_no)
                .limit(limit)
                .offset(offset)
            )
        )

    def create_source(self, payload: c.SourceCreate):
        self.check_provenance(payload)
        data = payload.model_dump()
        data["metadata_"] = data.pop("metadata")
        return self.store.add(m.Source(**data))

    def create_evidence(self, hypothesis_id, payload: c.EvidenceCreate):
        hypothesis = self.store.lock_hypothesis(hypothesis_id)
        self.check_provenance(payload)
        version = self.version_for(hypothesis, payload.hypothesis_version_id)
        if payload.source_id:
            self.store.require(m.Source, payload.source_id)
        return self.store.add(
            m.Evidence(
                **payload.model_dump(exclude={"hypothesis_version_id"}),
                hypothesis_version_id=version.id,
            )
        )

    def version_records(self, model, hypothesis_id, limit=100, offset=0):
        self.store.require(m.Hypothesis, hypothesis_id)
        return list(
            self.session.scalars(
                select(model)
                .join(m.HypothesisVersion, model.hypothesis_version_id == m.HypothesisVersion.id)
                .where(m.HypothesisVersion.hypothesis_id == hypothesis_id)
                .order_by(model.created_at, model.id)
                .limit(limit)
                .offset(offset)
            )
        )

    def create_experiment(self, hypothesis_id, payload: c.ExperimentCreate):
        hypothesis = self.store.lock_hypothesis(hypothesis_id)
        self.check_provenance(payload)
        version = self.version_for(hypothesis, payload.hypothesis_version_id)
        return self.store.add(
            m.Experiment(
                **payload.model_dump(exclude={"hypothesis_version_id"}),
                hypothesis_version_id=version.id,
            )
        )

    def create_signal(self, experiment_id, payload: c.SignalCreate):
        self.store.require(m.Experiment, experiment_id)
        self.check_provenance(payload)
        return self.store.add(m.Signal(experiment_id=experiment_id, **payload.model_dump()))

    def signals(self, experiment_id, **page):
        self.store.require(m.Experiment, experiment_id)
        return self.store.list(m.Signal, m.Signal.experiment_id == experiment_id, **page)

    def create_decision(self, hypothesis_id, payload: c.DecisionCreate):
        hypothesis = self.store.lock_hypothesis(hypothesis_id)
        self.check_provenance(payload)
        version = self.version_for(hypothesis, payload.from_version_id)
        target = DECISION_TARGETS.get(payload.decision)
        if target:
            if version.id != hypothesis.current_version_id:
                raise DomainError("State-changing decisions must use the current version", 422)
            validate_transition(hypothesis.status, target)
        if payload.to_version_id:
            self.version_for(hypothesis, payload.to_version_id)
        for evidence_id in set(payload.supporting_evidence_ids):
            evidence = self.store.require(m.Evidence, evidence_id)
            self.version_for(hypothesis, evidence.hypothesis_version_id)
        for signal_id in set(payload.supporting_signal_ids):
            signal = self.store.require(m.Signal, signal_id)
            experiment = self.store.require(m.Experiment, signal.experiment_id)
            self.version_for(hypothesis, experiment.hypothesis_version_id)
        decision = self.store.add(
            m.DecisionLog(
                hypothesis_id=hypothesis.id,
                from_version_id=version.id,
                **payload.model_dump(
                    exclude={"from_version_id", "supporting_evidence_ids", "supporting_signal_ids"}
                ),
            )
        )
        for evidence_id in set(payload.supporting_evidence_ids):
            self.store.add(m.DecisionEvidence(decision_id=decision.id, evidence_id=evidence_id))
        for signal_id in set(payload.supporting_signal_ids):
            self.store.add(m.DecisionSignal(decision_id=decision.id, signal_id=signal_id))
        if target:
            self._transition(hypothesis, target, payload.rationale, payload, decision.id)
        return self.decision_read(decision)

    def decision_read(self, decision):
        result = c.DecisionRead.model_validate(decision)
        result.supporting_evidence_ids = list(
            self.session.scalars(
                select(m.DecisionEvidence.evidence_id)
                .where(m.DecisionEvidence.decision_id == decision.id)
                .order_by(m.DecisionEvidence.evidence_id)
            )
        )
        result.supporting_signal_ids = list(
            self.session.scalars(
                select(m.DecisionSignal.signal_id)
                .where(m.DecisionSignal.decision_id == decision.id)
                .order_by(m.DecisionSignal.signal_id)
            )
        )
        result.resulting_version_ids = list(
            self.session.scalars(
                select(m.HypothesisVersion.id)
                .where(m.HypothesisVersion.originating_decision_id == decision.id)
                .order_by(m.HypothesisVersion.version_no)
            )
        )
        return result

    def decisions(self, hypothesis_id, **page):
        self.store.require(m.Hypothesis, hypothesis_id)
        return [
            self.decision_read(row)
            for row in self.store.list(
                m.DecisionLog, m.DecisionLog.hypothesis_id == hypothesis_id, **page
            )
        ]

    def create_agent_run(self, payload: c.AgentRunCreate):
        return self.store.add(m.AgentRun(**payload.model_dump()))

    def create_review(self, payload: c.HumanReviewCreate):
        targets = {
            "hypothesis_version_id": m.HypothesisVersion,
            "experiment_id": m.Experiment,
            "decision_id": m.DecisionLog,
            "agent_run_id": m.AgentRun,
        }
        for field, model in targets.items():
            if identifier := getattr(payload, field):
                target = self.store.require(model, identifier)
                if (
                    model is m.AgentRun
                    and target.agent_role == ROLE
                    and target.run_type == RUN_TYPE
                    and target.status != RunStatus.succeeded
                ):
                    raise DomainError("Research must succeed before human review", 409)
        return self.store.add(m.HumanReview(**payload.model_dump()))
