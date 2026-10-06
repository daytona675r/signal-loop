from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from signalloop.models.entities import AgentRun, Evidence, Source
from signalloop.research.contracts import ResearchCommand, ResearchResult, SourceMaterial
from signalloop.research.worker import ROLE, ResearchFailed, ResearchWorker
from signalloop.services.backbone import Backbone


def material(identifier="123"):
    return SourceMaterial(
        url=f"https://news.ycombinator.com/item?id={identifier}",
        external_id=identifier,
        title="Storage discussion",
        captured_at=datetime.now(UTC),
        quote="I don't want to drill holes.",
        metadata={"author": "fixture-user", "simulated": True},
    )


def test_source_evidence_and_run_commit_together(engine, client, hypothesis, hypothesis_payload):
    sessions = sessionmaker(engine)
    root = f"/hypotheses/{hypothesis['id']}"

    def collect(work):
        # A new version appears while external work is in flight.
        response = client.post(root + "/versions", json=hypothesis_payload["version"])
        assert response.status_code == 201
        return ResearchResult(hypothesis_version_id=work.version.id, materials=[material()])

    result = ResearchWorker(sessions, collect).run(
        ResearchCommand(
            hypothesis_version_id=hypothesis["current_version_id"],
            query="storage",
        )
    )
    assert len(result.source_ids) == len(result.evidence_ids) == 1
    with sessions() as session:
        source = session.get(Source, result.source_ids[0])
        evidence = session.get(Evidence, result.evidence_ids[0])
        run = session.get(AgentRun, result.agent_run_id)
        assert source.url == "https://news.ycombinator.com/item?id=123"
        assert source.metadata_["author"] == "fixture-user"
        assert len(source.source_hash) == 64
        assert evidence.source_id == source.id
        assert evidence.hypothesis_version_id == UUID(hypothesis["current_version_id"])
        assert evidence.stance == "unknown"
        assert evidence.structured_facts["relevance"] == "unassessed"
        for row in (source, evidence):
            assert row.created_by_type == "agent"
            assert row.created_by == ROLE
            assert row.agent_run_id == run.id
        assert run.status == "succeeded"
        assert run.output_snapshot == result.model_dump(mode="json")
    assert client.get(root).json()["current_version_id"] != hypothesis["current_version_id"]
    assert client.get(root).json()["status"] == "DRAFT"
    assert client.get(root + "/decisions").json() == []


@pytest.mark.parametrize("fail_after", ["source", "first_evidence"])
def test_partial_persistence_rolls_back_but_failure_trace_survives(
    engine,
    hypothesis,
    monkeypatch,
    fail_after,
):
    sessions = sessionmaker(engine)
    original = Backbone.create_evidence

    def fail(service, hypothesis_id, payload):
        if fail_after == "first_evidence":
            original(service, hypothesis_id, payload)
        raise RuntimeError("Simulated failure after partial persistence")

    monkeypatch.setattr(Backbone, "create_evidence", fail)

    def collect(work):
        return ResearchResult(
            hypothesis_version_id=work.version.id, materials=[material(), material("456")]
        )

    with pytest.raises(ResearchFailed) as error:
        ResearchWorker(sessions, collect).run(
            ResearchCommand(
                hypothesis_version_id=hypothesis["current_version_id"],
                query="storage",
            )
        )
    with sessions() as session:
        run = session.get(AgentRun, error.value.run_id)
        assert run.status == "failed"
        assert run.error.startswith("persistence:")
        assert run.output_snapshot == {}
        assert list(session.scalars(select(Source).where(Source.agent_run_id == run.id))) == []
        assert list(session.scalars(select(Evidence).where(Evidence.agent_run_id == run.id))) == []


def test_repeat_run_has_explicit_separate_provenance(engine, hypothesis):
    sessions = sessionmaker(engine)

    def collect(work):
        return ResearchResult(hypothesis_version_id=work.version.id, materials=[material()])

    worker = ResearchWorker(sessions, collect)
    command = ResearchCommand(
        hypothesis_version_id=hypothesis["current_version_id"], query="storage"
    )
    first, second = worker.run(command), worker.run(command)
    assert first.agent_run_id != second.agent_run_id
    assert first.source_ids != second.source_ids
    assert first.evidence_ids != second.evidence_ids
