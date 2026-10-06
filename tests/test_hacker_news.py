import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from signalloop.models.entities import AgentRun
from signalloop.research.contracts import ResearchCommand, ResearchInput
from signalloop.research.hacker_news import ENDPOINT, HackerNewsComments
from signalloop.research.worker import ResearchFailed, ResearchWorker
from signalloop.schemas.contracts import VersionRead


def work(client, hypothesis, limit=5):
    version = VersionRead.model_validate(
        client.get(f"/hypotheses/{hypothesis['id']}/versions/1").json()
    )
    return ResearchInput(
        command=ResearchCommand(hypothesis_version_id=version.id, query="van storage", limit=limit),
        version=version,
    )


def test_single_request_normalizes_attributable_comment(client, hypothesis):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "objectID": "1234",
                        "comment_text": "<p>I don't want <em>holes</em> &amp; rattles.</p>",
                        "story_title": "Van storage",
                        "author": "someone",
                        "created_at": "2026-01-01T00:00:00Z",
                        "story_url": "https://example.org/van",
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = HackerNewsComments(http).collect(work(client, hypothesis))
    assert len(calls) == 1
    assert str(calls[0].url).startswith(ENDPOINT)
    assert dict(calls[0].url.params) == {
        "query": "van storage",
        "tags": "comment",
        "hitsPerPage": "5",
        "page": "0",
    }
    item = result.materials[0]
    assert str(item.url) == "https://news.ycombinator.com/item?id=1234"
    assert item.quote == "I don't want holes & rattles."
    assert item.metadata["author"] == "someone"
    assert item.captured_at.tzinfo is not None
    assert item.external_id == "1234"


@pytest.mark.parametrize(
    "hits,skipped",
    [
        ([], 0),
        ([{"objectID": "1", "comment_text": None}], 1),
        ([{"objectID": "1", "comment_text": "[deleted]"}], 1),
    ],
)
def test_empty_result_is_explicit(client, hypothesis, hits, skipped):
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"hits": hits}))
    ) as http:
        result = HackerNewsComments(http).collect(work(client, hypothesis))
    assert result.materials == []
    assert result.skipped_items == skipped


@pytest.mark.parametrize("case", ["http", "timeout", "json", "invalid", "oversize", "redirect"])
def test_adapter_failure_is_durable_without_retry(engine, hypothesis, case):
    calls = []

    def handler(request):
        calls.append(request)
        if case == "timeout":
            raise httpx.ReadTimeout("Timed out", request=request)
        if case == "http":
            return httpx.Response(503)
        if case == "redirect":
            return httpx.Response(302, headers={"location": "https://example.org"})
        if case == "json":
            return httpx.Response(200, content=b"not json")
        if case == "oversize":
            return httpx.Response(200, content=b" " * 2_000_001)
        return httpx.Response(
            200, json={"hits": [{"objectID": "not-an-id", "comment_text": "Text"}]}
        )

    sessions = sessionmaker(engine)
    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as http,
        pytest.raises(ResearchFailed) as error,
    ):
        ResearchWorker(sessions, HackerNewsComments(http).collect).run(
            ResearchCommand(
                hypothesis_version_id=hypothesis["current_version_id"],
                query="storage",
            )
        )
    assert len(calls) == 1
    with sessions() as session:
        run = session.get(AgentRun, error.value.run_id)
        assert run.status == "failed"
        assert run.output_snapshot == {}
        assert run.error.startswith("source:")


def test_excess_results_rejected(client, hypothesis):
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={
                        "hits": [{"objectID": "1", "comment_text": "x"}] * 2,
                    },
                )
            )
        ) as http,
        pytest.raises(ValueError, match="more items"),
    ):
        HackerNewsComments(http).collect(work(client, hypothesis, limit=1))
