from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from signalloop.domain.states import DomainError
from signalloop.research.contracts import ResearchCommand, ResearchResult
from signalloop.research.worker import ResearchWorker


def test_explicit_old_version_is_loaded(engine, client, hypothesis, hypothesis_payload):
    root = f"/hypotheses/{hypothesis['id']}"
    assert (
        client.post(
            root + "/versions",
            json={
                **hypothesis_payload["version"],
                "price_assumption": "349.00",
            },
        ).status_code
        == 201
    )
    before = client.get(root).json()
    seen = []

    def collect(work):
        seen.append(work)
        return ResearchResult(hypothesis_version_id=work.version.id)

    result = ResearchWorker(sessionmaker(engine), collect).run(
        ResearchCommand(
            hypothesis_version_id=hypothesis["current_version_id"],
            query="van storage",
        )
    )
    assert result.hypothesis_version_id == UUID(hypothesis["current_version_id"])
    assert seen[0].version.version_no == 1
    assert str(seen[0].version.price_assumption) == "449.00"
    assert client.get(root).json() == before
    assert client.get(root + "/decisions").json() == []
    assert client.get(root + "/experiments").json() == []


def test_missing_version_never_calls_source(engine):
    def collect(_):
        pytest.fail("Source must not be called for an unknown version")

    with pytest.raises(DomainError, match="not found") as error:
        ResearchWorker(sessionmaker(engine), collect).run(
            ResearchCommand(
                hypothesis_version_id=uuid4(),
                query="storage",
            )
        )
    assert error.value.status_code == 404


def test_version_is_required_and_query_is_bounded():
    for payload in (
        {"query": "storage"},
        {"hypothesis_version_id": uuid4(), "query": " "},
        {"hypothesis_version_id": uuid4(), "query": "storage", "limit": 21},
    ):
        with pytest.raises(ValidationError):
            ResearchCommand(**payload)
