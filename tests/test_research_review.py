import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from signalloop.models.entities import AgentRun, DecisionLog, HumanReview, Signal
from signalloop.research.constants import ROLE, RUN_TYPE
from signalloop.research.contracts import ResearchCommand, ResearchResult
from signalloop.research.worker import ResearchWorker


@pytest.mark.parametrize("decision", ["approved", "rejected", "modified", "escalated"])
def test_success_waits_for_explicit_review(engine, client, hypothesis, decision):
    sessions = sessionmaker(engine)
    root = f"/hypotheses/{hypothesis['id']}"
    before = {
        path: client.get(root + path).json()
        for path in ("", "/versions", "/history", "/experiments")
    }
    with sessions() as session:
        counts = {
            model: session.scalar(select(func.count()).select_from(model))
            for model in (HumanReview, DecisionLog, Signal)
        }
    result = ResearchWorker(
        sessions, lambda work: ResearchResult(hypothesis_version_id=work.version.id)
    ).run(ResearchCommand(hypothesis_version_id=hypothesis["current_version_id"], query="storage"))
    run_id = str(result.agent_run_id)
    assert str(result.review_target.agent_run_id) == run_id
    with sessions() as session:
        for model, count in counts.items():
            assert session.scalar(select(func.count()).select_from(model)) == count
    listing = (
        "/research-runs?awaiting_review=true"
        f"&hypothesis_version_id={hypothesis['current_version_id']}"
    )
    assert [row["id"] for row in client.get(listing).json()] == [run_id]
    before_review = client.get(f"/research-runs/{run_id}").json()
    assert before_review["review_status"] == "awaiting_review"
    assert before_review["review_ids"] == []
    assert before_review["review_target"] == {"agent_run_id": run_id}
    response = client.post(
        "/human-reviews",
        json={
            **before_review["review_target"],
            "decision": decision,
            "notes": "Explicit human action",
            "reviewed_by": "reviewer",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["agent_run_id"] == run_id
    assert client.get(listing).json() == []
    reviewed = client.get(f"/research-runs/{run_id}").json()
    assert reviewed["review_status"] == "reviewed"
    assert reviewed["latest_review_decision"] == decision
    assert reviewed["review_ids"] == [response.json()["id"]]
    for path, value in before.items():
        assert client.get(root + path).json() == value
    with sessions() as session:
        for model in (DecisionLog, Signal):
            assert session.scalar(select(func.count()).select_from(model)) == counts[model]
        assert session.get(AgentRun, result.agent_run_id).status == "succeeded"


@pytest.mark.parametrize("status", ["pending", "running", "failed"])
def test_unfinished_or_failed_research_cannot_be_reviewed(engine, client, hypothesis, status):
    with sessionmaker(engine)() as session, session.begin():
        run = AgentRun(
            agent_role=ROLE,
            run_type=RUN_TYPE,
            status=status,
            hypothesis_version_id=hypothesis["current_version_id"],
        )
        session.add(run)
        session.flush()
        identifier = str(run.id)
    response = client.post(
        "/human-reviews",
        json={
            "agent_run_id": identifier,
            "decision": "approved",
            "notes": "Premature",
            "reviewed_by": "human",
        },
    )
    assert response.status_code == 409
    assert client.get(f"/research-runs/{identifier}").json()["review_status"] == "not_ready"
    assert client.get(f"/research-runs/{identifier}").json()["review_target"] is None


def test_other_agent_runs_are_not_research_targets(client):
    run = client.post(
        "/agent-runs", json={"agent_role": "another-worker", "run_type": "test"}
    ).json()
    assert client.get(f"/research-runs/{run['id']}").status_code == 404
