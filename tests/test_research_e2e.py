"""Foundation v0.2 acceptance: real adapter, real PostgreSQL, explicit human boundary."""

from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from signalloop.domain.states import DomainError
from signalloop.models.entities import AgentRun, Evidence, Source
from signalloop.research.contracts import ResearchCommand
from signalloop.research.hacker_news import HackerNewsComments
from signalloop.research.worker import ResearchFailed, ResearchWorker
from signalloop.services.backbone import Backbone


def source_response(request):
    return httpx.Response(
        200,
        json={
            "hits": [
                {
                    "objectID": "123456",
                    "story_title": "Storage discussion (test fixture)",
                    "comment_text": "<p>I want storage I can remove without drilling.</p>",
                    "author": "fixture-user",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ]
        },
    )


def test_foundation_v02_full_acceptance(engine, client, hypothesis, hypothesis_payload):
    root = f"/hypotheses/{hypothesis['id']}"
    version_id = hypothesis["current_version_id"]
    before = {
        path: client.get(root + path).json()
        for path in ("", "/versions", "/history", "/decisions", "/experiments")
    }
    sessions = sessionmaker(engine)
    with httpx.Client(transport=httpx.MockTransport(source_response)) as http:
        result = ResearchWorker(sessions, HackerNewsComments(http).collect).run(
            ResearchCommand(
                hypothesis_version_id=version_id,
                query="removable storage",
                limit=1,
            )
        )
    run_id = str(result.agent_run_id)
    run = client.get(f"/research-runs/{run_id}").json()
    assert run["status"] == "succeeded"
    assert run["review_status"] == "awaiting_review"
    assert run["review_ids"] == []  # No invented human action.
    assert run["input_snapshot"]["command"]["hypothesis_version_id"] == version_id
    assert run["hypothesis_version_id"] == version_id
    assert run["input_snapshot"]["version"]["version_no"] == 1
    assert run["started_at"] <= run["finished_at"]
    assert run["output_snapshot"] == result.model_dump(mode="json")
    source = client.get(f"/sources/{result.source_ids[0]}").json()
    evidence = client.get(root + "/evidence").json()
    assert len(evidence) == 1
    assert evidence[0]["source_id"] == source["id"]
    assert source["external_id"] == "123456"
    assert source["url"] == "https://news.ycombinator.com/item?id=123456"
    assert source["metadata"]["author"] == "fixture-user"
    assert evidence[0]["quote_or_summary"] == "I want storage I can remove without drilling."
    assert evidence[0]["hypothesis_version_id"] == version_id
    assert evidence[0]["agent_run_id"] == source["agent_run_id"] == run_id
    assert evidence[0]["stance"] == "unknown"
    for path, original in before.items():
        assert client.get(root + path).json() == original
    review = client.post(
        "/human-reviews",
        json={
            **run["review_target"],
            "decision": "approved",
            "notes": "Human examined source excerpt",
            "reviewed_by": "acceptance-reviewer",
        },
    )
    assert review.status_code == 201
    assert review.json()["agent_run_id"] == run_id
    assert client.get(f"/research-runs/{run_id}").json()["latest_review_decision"] == "approved"
    for path, original in before.items():
        assert client.get(root + path).json() == original
    # A separate manual change never rebinds old research evidence.
    v2 = client.post(
        root + "/versions", json={**hypothesis_payload["version"], "price_assumption": "349.00"}
    )
    assert v2.status_code == 201
    assert client.get(root + "/evidence").json() == evidence
    assert client.get(f"/research-runs/{run_id}").json()["hypothesis_version_id"] == version_id


@pytest.mark.parametrize("failure", ["adapter", "validation", "database"])
def test_e2e_failures_retain_only_failed_run(engine, client, hypothesis, monkeypatch, failure):
    def response(request):
        if failure == "adapter":
            return httpx.Response(503)
        if failure == "validation":
            return httpx.Response(200, json={"hits": [{"objectID": "bad", "comment_text": "x"}]})
        return source_response(request)

    if failure == "database":
        # Exercise a real FK error after the Source has already been flushed.
        def insert_orphan(service, hypothesis_id, payload):
            service.session.add(
                Evidence(
                    hypothesis_version_id=payload.hypothesis_version_id,
                    source_id=uuid4(),
                    quote_or_summary=payload.quote_or_summary,
                )
            )
            service.session.flush()

        monkeypatch.setattr(Backbone, "create_evidence", insert_orphan)
    sessions = sessionmaker(engine)
    with (
        httpx.Client(transport=httpx.MockTransport(response)) as http,
        pytest.raises(ResearchFailed) as error,
    ):
        ResearchWorker(sessions, HackerNewsComments(http).collect).run(
            ResearchCommand(
                hypothesis_version_id=hypothesis["current_version_id"],
                query="storage",
            )
        )
    run_id = error.value.run_id
    with sessions() as session:
        run = session.get(AgentRun, run_id)
        assert run.status == "failed"
        assert run.hypothesis_version_id == UUID(hypothesis["current_version_id"])
        assert run.input_snapshot and run.error and run.finished_at
        assert run.output_snapshot == {}
        if failure == "database":
            assert "IntegrityError" in run.error
        for model in (Source, Evidence):
            assert list(session.scalars(select(model).where(model.agent_run_id == run_id))) == []
    assert client.get(f"/research-runs/{run_id}").json()["review_status"] == "not_ready"
    assert client.get(f"/hypotheses/{hypothesis['id']}/evidence").json() == []
    assert client.get(f"/hypotheses/{hypothesis['id']}").json() == hypothesis


def test_e2e_unknown_version_has_zero_side_effects(engine):
    sessions = sessionmaker(engine)
    with sessions() as session:
        before = {
            model: session.scalar(select(func.count()).select_from(model))
            for model in (AgentRun, Source, Evidence)
        }

    def unexpected(_):
        pytest.fail("Network request must never occur")

    with (
        httpx.Client(transport=httpx.MockTransport(unexpected)) as http,
        pytest.raises(DomainError) as error,
    ):
        ResearchWorker(sessions, HackerNewsComments(http).collect).run(
            ResearchCommand(
                hypothesis_version_id=uuid4(),
                query="storage",
            )
        )
    assert error.value.status_code == 404
    with sessions() as session:
        for model, count in before.items():
            assert session.scalar(select(func.count()).select_from(model)) == count
