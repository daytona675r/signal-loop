"""Synchronous research with separately committed, durable execution provenance."""

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from time import monotonic
from uuid import UUID

from sqlalchemy.orm import Session

from signalloop.domain.states import DomainError, RunStatus
from signalloop.models.entities import AgentRun, HypothesisVersion
from signalloop.repositories.store import Store
from signalloop.research.contracts import ResearchCommand, ResearchInput, ResearchResult
from signalloop.schemas.contracts import EvidenceCreate, SourceCreate, VersionRead
from signalloop.services.backbone import Backbone

ROLE = "research-worker-v0.2"
RUN_TYPE = "hacker_news_research"


class ResearchFailed(DomainError):
    def __init__(self, run_id: UUID):
        self.run_id = run_id
        super().__init__(f"Research failed; inspect AgentRun {run_id}", 502)


class ResearchWorker:
    def __init__(
        self,
        sessions: Callable[[], Session],
        collect: Callable[[ResearchInput], ResearchResult],
    ):
        self.sessions = sessions
        self.collect = collect

    def _pending(self, work: ResearchInput) -> UUID:
        with self.sessions() as session, session.begin():
            run = AgentRun(
                agent_role=ROLE,
                run_type=RUN_TYPE,
                status=RunStatus.pending,
                hypothesis_version_id=work.version.id,
                input_snapshot=work.model_dump(mode="json"),
            )
            session.add(run)
            session.flush()
            return run.id

    def _running(self, run_id):
        with self.sessions() as session, session.begin():
            run = Store(session).require(AgentRun, run_id)
            run.status = RunStatus.running
            run.started_at = datetime.now(UTC)

    def _succeed(self, session, run, result):
        service = Backbone(session)
        version = Store(session).require(HypothesisVersion, result.hypothesis_version_id)
        actor = {"created_by_type": "agent", "created_by": ROLE, "agent_run_id": run.id}
        for item in result.materials:
            source = service.create_source(
                SourceCreate(
                    url=str(item.url),
                    platform="Hacker News",
                    source_type=result.source_type,
                    title=item.title,
                    external_id=item.external_id,
                    captured_at=item.captured_at,
                    source_hash=sha256(item.quote.encode()).hexdigest(),
                    metadata=item.metadata,
                    **actor,
                )
            )
            evidence = service.create_evidence(
                version.hypothesis_id,
                EvidenceCreate(
                    hypothesis_version_id=version.id,
                    source_id=source.id,
                    stance="unknown",
                    quote_or_summary=item.quote,
                    structured_facts={
                        "kind": "source_excerpt",
                        "relevance": "unassessed",
                        "external_id": item.external_id,
                    },
                    **actor,
                ),
            )
            result.source_ids.append(source.id)
            result.evidence_ids.append(evidence.id)
        run.output_snapshot = result.model_dump(mode="json")
        run.status = RunStatus.succeeded

    def run(self, command: ResearchCommand) -> ResearchResult:
        with self.sessions() as session:
            version = Store(session).require(HypothesisVersion, command.hypothesis_version_id)
            work = ResearchInput(command=command, version=VersionRead.model_validate(version))
        run_id = self._pending(work)
        started = monotonic()
        stage = "start"
        try:
            self._running(run_id)
            stage = "source"
            raw_result = self.collect(work)
            stage = "validation"
            result = ResearchResult.model_validate(raw_result)
            if result.hypothesis_version_id != command.hypothesis_version_id:
                raise DomainError("Research output references a different version", 422)
            if len(result.materials) > command.limit:
                raise DomainError("Research output exceeds the requested limit", 422)
            result = result.model_copy(
                update={"agent_run_id": run_id, "source_ids": [], "evidence_ids": []}
            )
            stage = "persistence"
            with self.sessions() as session, session.begin():
                run = Store(session).require(AgentRun, run_id)
                self._succeed(session, run, result)
                run.finished_at = datetime.now(UTC)
                run.latency_ms = int((monotonic() - started) * 1000)
            return result
        except Exception as error:
            # The failed work transaction has exited/rolled back before this fresh transaction.
            with self.sessions() as session, session.begin():
                run = Store(session).require(AgentRun, run_id)
                run.status = RunStatus.failed
                run.finished_at = datetime.now(UTC)
                run.latency_ms = int((monotonic() - started) * 1000)
                run.error = f"{stage}: {type(error).__name__}: {error}"[:20000]
                run.output_snapshot = {}
            raise ResearchFailed(run_id) from error
