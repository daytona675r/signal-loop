from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from signalloop.domain.states import DomainError
from signalloop.models.entities import AgentRun
from signalloop.research.contracts import ResearchCommand, ResearchResult
from signalloop.research.worker import ResearchFailed, ResearchWorker


def test_committed_pending_running_success(engine, hypothesis, monkeypatch):
    sessions = sessionmaker(engine)
    command = ResearchCommand(
        hypothesis_version_id=hypothesis["current_version_id"], query="storage"
    )

    def collect(work):
        with sessions() as session:
            run = session.scalar(
                select(AgentRun).where(AgentRun.hypothesis_version_id == work.version.id)
            )
            assert run.status == "running"
            assert run.started_at is not None and run.finished_at is None
            assert run.input_snapshot["command"] == command.model_dump(mode="json")
            assert run.input_snapshot["version"]["version_no"] == 1
            assert run.output_snapshot == {}
        return ResearchResult(hypothesis_version_id=work.version.id)

    worker = ResearchWorker(sessions, collect)
    original_running = worker._running

    def observe_pending(run_id):
        with sessions() as session:
            run = session.get(AgentRun, run_id)
            assert run.status == "pending"
            assert run.started_at is None and run.finished_at is None
        original_running(run_id)

    monkeypatch.setattr(worker, "_running", observe_pending)
    result = worker.run(command)
    with sessions() as session:
        run = session.get(AgentRun, result.agent_run_id)
        assert run.status == "succeeded"
        assert run.started_at <= run.finished_at
        assert run.latency_ms >= 0
        assert run.error is None
        assert run.output_snapshot == result.model_dump(mode="json")
        assert run.hypothesis_version_id == UUID(hypothesis["current_version_id"])


@pytest.mark.parametrize("failure", ["source", "validation", "wrong_version", "persistence"])
def test_failures_are_durable(engine, hypothesis, monkeypatch, failure):
    sessions = sessionmaker(engine)

    def collect(work):
        if failure == "source":
            raise RuntimeError("Adapter unavailable")
        if failure == "validation":
            return {"materials": "invalid"}
        return ResearchResult(
            hypothesis_version_id=uuid4() if failure == "wrong_version" else work.version.id
        )

    worker = ResearchWorker(sessions, collect)
    if failure == "persistence":

        def fail(session, run, result):
            run.status = "succeeded"
            run.output_snapshot = result.model_dump(mode="json")
            session.flush()
            raise RuntimeError("Persistence interrupted")

        monkeypatch.setattr(worker, "_succeed", fail)
    with pytest.raises(ResearchFailed) as error:
        worker.run(
            ResearchCommand(hypothesis_version_id=hypothesis["current_version_id"], query="storage")
        )
    with sessions() as session:
        run = session.get(AgentRun, error.value.run_id)
        assert run.status == "failed"
        assert run.output_snapshot == {}
        assert run.finished_at >= run.started_at
        assert run.error
        assert run.input_snapshot["version"]["id"] == hypothesis["current_version_id"]


def test_missing_version_creates_no_run(engine):
    sessions = sessionmaker(engine)
    with sessions() as session:
        before = set(session.scalars(select(AgentRun.id)))
    with pytest.raises(DomainError):
        ResearchWorker(sessions, lambda _: pytest.fail("Unexpected call")).run(
            ResearchCommand(hypothesis_version_id=uuid4(), query="storage")
        )
    with sessions() as session:
        assert set(session.scalars(select(AgentRun.id))) == before
