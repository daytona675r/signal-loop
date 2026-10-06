"""Expose completed runs as explicit review targets without creating approvals."""

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from signalloop.domain.states import DomainError, RunStatus
from signalloop.models.entities import AgentRun, HumanReview
from signalloop.repositories.store import Store
from signalloop.research.constants import ROLE, RUN_TYPE
from signalloop.research.contracts import ResearchRunRead, ReviewTarget
from signalloop.schemas.contracts import AgentRunRead


class ResearchReviews:
    def __init__(self, session: Session):
        self.session = session

    def read(self, run_id):
        run = Store(self.session).require(AgentRun, run_id)
        if run.agent_role != ROLE or run.run_type != RUN_TYPE:
            raise DomainError("Research run not found", 404)
        reviews = list(
            self.session.scalars(
                select(HumanReview)
                .where(HumanReview.agent_run_id == run.id)
                .order_by(HumanReview.created_at, HumanReview.id)
            )
        )
        ready = run.status == RunStatus.succeeded
        status = "not_ready" if not ready else "reviewed" if reviews else "awaiting_review"
        return ResearchRunRead(
            **AgentRunRead.model_validate(run).model_dump(),
            review_status=status,
            review_target=ReviewTarget(agent_run_id=run.id) if ready else None,
            review_ids=[review.id for review in reviews],
            latest_review_decision=reviews[-1].decision if reviews else None,
        )

    def list(self, hypothesis_version_id=None, awaiting_review=False, limit=100, offset=0):
        query = select(AgentRun.id).where(
            AgentRun.agent_role == ROLE, AgentRun.run_type == RUN_TYPE
        )
        if hypothesis_version_id is not None:
            query = query.where(AgentRun.hypothesis_version_id == hypothesis_version_id)
        if awaiting_review:
            query = query.where(
                AgentRun.status == RunStatus.succeeded,
                ~exists().where(HumanReview.agent_run_id == AgentRun.id),
            )
        query = query.order_by(AgentRun.created_at, AgentRun.id).limit(limit).offset(offset)
        return [self.read(identifier) for identifier in self.session.scalars(query)]
