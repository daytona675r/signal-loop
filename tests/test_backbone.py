from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from signalloop.models import entities as m
from signalloop.schemas.contracts import VersionCreate
from signalloop.services.backbone import Backbone


def post(client, path, data):
    response = client.post(path, json=data)
    assert response.status_code == 201, response.text
    return response.json()


def move(client, identifier, state):
    return post(
        client,
        f"/hypotheses/{identifier}/transition",
        {
            "target_state": state,
            "reason": f"Manual move to {state}",
            "created_by": "mario",
        },
    )


def test_full_acceptance_loop(client, hypothesis, hypothesis_payload):
    identifier = hypothesis["id"]
    root = f"/hypotheses/{identifier}"
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get(root).json() == hypothesis
    v1 = client.get(root + "/versions/1").json()
    assert v1["version_no"] == 1
    assert v1["id"] == hypothesis["current_version_id"]
    assert v1["price_assumption"] == "449.00"
    move(client, identifier, "FEASIBILITY")
    move(client, identifier, "RESEARCH")
    source = post(
        client,
        "/sources",
        {
            "source_type": "manual_observation",
            "title": "Example observation",
            "created_by": "mario",
            "metadata": {"example": True},
        },
    )
    assert client.get(f"/sources/{source['id']}").json()["metadata"] == {"example": True}
    evidence = post(
        client,
        root + "/evidence",
        {
            "source_id": source["id"],
            "stance": "supports",
            "strength": "0.5",
            "quote_or_summary": "I don't want to drill holes into my van.",
            "created_by": "mario",
        },
    )
    assert evidence["hypothesis_version_id"] == v1["id"]
    assert client.get(f"/evidence/{evidence['id']}").status_code == 200
    move(client, identifier, "READY_FOR_EXPERIMENT")
    experiment = post(
        client,
        root + "/experiments",
        {
            "name": "Landing Page Demand Test",
            "objective": "Measure CTA conversion rate",
            "channel": "manual example",
            "success_criteria": "CTA conversion rate >= 5%",
            "price_test": "449.00",
        },
    )
    assert client.get(f"/experiments/{experiment['id']}").json() == experiment
    move(client, identifier, "EXPERIMENT")
    signals = [
        post(
            client,
            f"/experiments/{experiment['id']}/signals",
            {
                "signal_type": kind,
                "value": 1,
                "occurred_at": datetime.now(UTC).isoformat(),
                "observation": f"Manually simulated {kind}; not real market validation",
                "raw_payload": {"simulated": True},
            },
        )
        for kind in ("page_view", "email_submit", "price_objection")
    ]
    assert len(client.get(f"/experiments/{experiment['id']}/signals").json()) == 3
    move(client, identifier, "EVALUATION")
    decision = post(
        client,
        root + "/decisions",
        {
            "decision": "iterate",
            "rationale": (
                "Problem evidence looks promising, but price sensitivity still needs validation."
            ),
            "supporting_evidence_ids": [evidence["id"]],
            "supporting_signal_ids": [row["id"] for row in signals],
        },
    )
    assert client.get(root).json()["status"] == "ITERATION"
    v2 = post(
        client,
        root + "/versions",
        {
            **hypothesis_payload["version"],
            "price_assumption": "349.00",
            "change_reason": "Test a lower price assumption",
            "originating_decision_id": decision["id"],
        },
    )
    assert v2["version_no"] == 2
    assert v2["price_assumption"] == "349.00"
    assert client.get(root + "/versions/1").json() == v1
    assert len(client.get(root + "/versions").json()) == 2
    assert client.get(root).json()["current_version_id"] == v2["id"]
    move(client, identifier, "RESEARCH")
    history = client.get(root + "/history").json()
    assert [row["to_state"] for row in history] == [
        "DRAFT",
        "FEASIBILITY",
        "RESEARCH",
        "READY_FOR_EXPERIMENT",
        "EXPERIMENT",
        "EVALUATION",
        "ITERATION",
        "RESEARCH",
    ]
    assert history[-2]["decision_id"] == decision["id"]
    assert history[-2]["hypothesis_version_id"] == v1["id"]
    assert history[-1]["hypothesis_version_id"] == v2["id"]
    stored_decision = client.get(root + "/decisions").json()[0]
    assert stored_decision["resulting_version_ids"] == [v2["id"]]
    assert stored_decision["supporting_evidence_ids"] == [evidence["id"]]
    assert set(stored_decision["supporting_signal_ids"]) == {row["id"] for row in signals}
    assert len(client.get(root + "/evidence").json()) == 1
    assert len(client.get(root + "/experiments").json()) == 1


def test_invalid_transition_and_decision_are_atomic(client, hypothesis):
    root = f"/hypotheses/{hypothesis['id']}"
    before = client.get(root + "/history").json()
    assert (
        client.post(
            root + "/transition",
            json={
                "target_state": "VALIDATED",
                "reason": "Cannot skip validation",
            },
        ).status_code
        == 409
    )
    assert (
        client.post(
            root + "/decisions",
            json={
                "decision": "iterate",
                "rationale": "Not in a state that allows iteration",
            },
        ).status_code
        == 409
    )
    assert client.get(root + "/history").json() == before
    assert client.get(root + "/decisions").json() == []
    assert client.get(root).json()["status"] == "DRAFT"


def test_optional_source_and_explicit_old_version(client, hypothesis, hypothesis_payload):
    root = f"/hypotheses/{hypothesis['id']}"
    post(client, root + "/versions", {**hypothesis_payload["version"], "change_reason": "Revise"})
    evidence = post(
        client,
        root + "/evidence",
        {
            "hypothesis_version_id": hypothesis["current_version_id"],
            "quote_or_summary": "A manually captured observation",
            "created_by": "mario",
        },
    )
    assert evidence["source_id"] is None
    assert evidence["hypothesis_version_id"] == hypothesis["current_version_id"]


def test_cross_hypothesis_references_rejected(client, hypothesis, hypothesis_payload):
    other = post(client, "/hypotheses", hypothesis_payload)
    root = f"/hypotheses/{hypothesis['id']}"
    assert (
        client.post(
            root + "/evidence",
            json={
                "hypothesis_version_id": other["current_version_id"],
                "quote_or_summary": "Wrong version",
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            root + "/experiments",
            json={
                "hypothesis_version_id": other["current_version_id"],
                "name": "Wrong version",
                "objective": "Test",
                "channel": "manual",
                "success_criteria": "Test",
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            root + "/decisions",
            json={
                "decision": "continue",
                "rationale": "Wrong version",
                "from_version_id": other["current_version_id"],
            },
        ).status_code
        == 422
    )
    evidence = post(client, f"/hypotheses/{other['id']}/evidence", {"quote_or_summary": "Other"})
    assert (
        client.post(
            root + "/decisions",
            json={
                "decision": "continue",
                "rationale": "Wrong evidence",
                "supporting_evidence_ids": [evidence["id"]],
            },
        ).status_code
        == 422
    )
    decision = post(
        client,
        f"/hypotheses/{other['id']}/decisions",
        {
            "decision": "continue",
            "rationale": "Continue research",
        },
    )
    assert (
        client.post(
            root + "/versions",
            json={
                **hypothesis_payload["version"],
                "originating_decision_id": decision["id"],
            },
        ).status_code
        == 422
    )
    assert client.get(root + "/decisions").json() == []


def test_agent_run_provenance_and_human_review(client, hypothesis):
    run = post(
        client,
        "/agent-runs",
        {
            "agent_role": "research-worker",
            "run_type": "manual-fixture",
            "provider": "example",
            "model": "future-model",
            "prompt_version": "v1",
            "status": "succeeded",
            "cost": "0.012345",
            "latency_ms": 35,
            "trace_id": "test-trace",
            "input_snapshot": {"version_id": hypothesis["current_version_id"]},
            "output_snapshot": {"interpretation": "No model was actually called"},
        },
    )
    assert client.get(f"/agent-runs/{run['id']}").json() == run
    evidence = post(
        client,
        f"/hypotheses/{hypothesis['id']}/evidence",
        {
            "quote_or_summary": "Manually entered worker result",
            "created_by_type": "agent",
            "created_by": "research-worker",
            "agent_run_id": run["id"],
        },
    )
    assert evidence["agent_run_id"] == run["id"]
    review = post(
        client,
        "/human-reviews",
        {
            "agent_run_id": run["id"],
            "decision": "approved",
            "notes": "Reviewed fixture",
            "reviewed_by": "mario",
        },
    )
    assert client.get(f"/human-reviews/{review['id']}").json() == review
    assert (
        client.post(
            "/human-reviews",
            json={
                "agent_run_id": run["id"],
                "hypothesis_version_id": hypothesis["current_version_id"],
                "decision": "approved",
                "notes": "Ambiguous",
                "reviewed_by": "mario",
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/human-reviews",
            json={
                "agent_run_id": str(uuid4()),
                "decision": "approved",
                "notes": "Missing",
                "reviewed_by": "mario",
            },
        ).status_code
        == 404
    )


def test_database_constraints_and_immutability(engine, client, hypothesis, hypothesis_payload):
    other = post(client, "/hypotheses", hypothesis_payload)
    statements = [
        (
            "UPDATE hypothesis_version SET price_assumption = 0 WHERE id = :id",
            {"id": hypothesis["current_version_id"]},
        ),
        ("DELETE FROM hypothesis_version WHERE id = :id", {"id": hypothesis["current_version_id"]}),
        (
            "UPDATE hypothesis SET current_version_id = :version WHERE id = :id",
            {"id": hypothesis["id"], "version": other["current_version_id"]},
        ),
        (
            "UPDATE hypothesis SET current_version_id = :version WHERE id = :id",
            {"id": hypothesis["id"], "version": uuid4()},
        ),
        (
            "UPDATE transition_history SET reason = 'rewrite' WHERE hypothesis_id = :id",
            {"id": hypothesis["id"]},
        ),
    ]
    for sql, params in statements:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text(sql), params)
    with Session(engine) as session, session.begin(), pytest.raises(IntegrityError):
        session.add(m.Evidence(hypothesis_version_id=uuid4(), quote_or_summary="Orphan"))
        session.flush()


def test_creation_rolls_back_on_failure(engine, hypothesis_payload, monkeypatch):
    from signalloop.schemas.contracts import HypothesisCreate

    with Session(engine) as session:
        before = set(session.scalars(select(m.Hypothesis.id)))
    with pytest.raises(RuntimeError), Session(engine) as session, session.begin():
        svc = Backbone(session)
        original = svc.store.add

        def fail_on_version(row):
            if isinstance(row, m.HypothesisVersion):
                raise RuntimeError("Simulated failure after hypothesis insert")
            return original(row)

        monkeypatch.setattr(svc.store, "add", fail_on_version)
        svc.create_hypothesis(HypothesisCreate(**hypothesis_payload))
    with Session(engine) as session:
        assert set(session.scalars(select(m.Hypothesis.id))) == before


def test_concurrent_versions_are_serialized(engine, hypothesis, hypothesis_payload):
    def create_version(index):
        with Session(engine) as session, session.begin():
            result = Backbone(session).create_version(
                hypothesis["id"],
                VersionCreate(
                    **{
                        **hypothesis_payload["version"],
                        "change_reason": f"Concurrent change {index}",
                    }
                ),
            )
            return result.version_no

    with ThreadPoolExecutor(max_workers=3) as executor:
        assert sorted(executor.map(create_version, range(3))) == [2, 3, 4]
    with Session(engine) as session:
        hypothesis_row = session.get(m.Hypothesis, hypothesis["id"])
        assert session.get(m.HypothesisVersion, hypothesis_row.current_version_id).version_no == 4


@pytest.mark.parametrize(
    "path,payload,code",
    [
        ("/hypotheses", {}, 422),
        ("/sources", {"source_type": " "}, 422),
        ("/sources", {"source_type": "manual", "url": "file:///secret"}, 422),
        ("/sources", {"source_type": "manual", "captured_at": "2026-01-01T10:00:00"}, 422),
        ("/sources", {"source_type": "manual", "unexpected": True}, 422),
        ("/human-reviews", {"decision": "approved", "notes": "No target", "reviewed_by": "m"}, 422),
    ],
)
def test_api_validation(client, path, payload, code):
    assert client.post(path, json=payload).status_code == code


def test_errors_and_pagination(client, hypothesis):
    assert client.get("/hypotheses/not-a-uuid").status_code == 422
    assert client.get(f"/hypotheses/{uuid4()}").status_code == 404
    assert client.get(f"/hypotheses/{uuid4()}/evidence").status_code == 404
    assert client.get(f"/hypotheses/{hypothesis['id']}/versions/999").status_code == 404
    assert client.get("/hypotheses?limit=0").status_code == 422
    assert client.get("/hypotheses?limit=201").status_code == 422
    assert len(client.get("/hypotheses?limit=1").json()) == 1
    assert client.get("/hypotheses?offset=1000000").json() == []
    assert (
        client.post(
            f"/hypotheses/{hypothesis['id']}/evidence",
            json={
                "quote_or_summary": "Test",
                "source_id": str(uuid4()),
            },
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/hypotheses/{hypothesis['id']}/versions/1",
            json={
                "price_assumption": 0,
            },
        ).status_code
        == 405
    )


def test_migration_matches_models(engine):
    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.check(config)
    assert set(inspect(engine).get_table_names()) == set(m.Base.metadata.tables) | {
        "alembic_version"
    }
