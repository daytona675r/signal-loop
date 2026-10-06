"""The sole source adapter: public Hacker News comment search via Algolia."""

from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Annotated

import httpx
from pydantic import BaseModel, Field
from pydantic.types import AwareDatetime

from signalloop.research.contracts import ResearchInput, ResearchResult, SourceMaterial

ENDPOINT = "https://hn.algolia.com/api/v1/search"
MAX_RESPONSE_BYTES = 2_000_000


class Comment(BaseModel):
    objectID: Annotated[str, Field(pattern=r"^[0-9]+$")]
    comment_text: str | None = None
    story_title: str | None = None
    story_url: str | None = None
    author: str | None = None
    created_at: AwareDatetime | None = None


class SearchResponse(BaseModel):
    hits: list[Comment]


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.ignored += 1
        elif tag in {"p", "br", "div", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.ignored = max(0, self.ignored - 1)
        elif tag in {"p", "div", "li"}:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def comment_text(html):
    parser = PlainText()
    parser.feed(html)
    parser.close()
    return " ".join("".join(parser.parts).split())


class HackerNewsComments:
    def __init__(self, client: httpx.Client):
        self.client = client

    def collect(self, work: ResearchInput) -> ResearchResult:
        # Fixed endpoint, no links followed, one request, no pagination or hidden retry.
        with self.client.stream(
            "GET",
            ENDPOINT,
            params={
                "query": work.command.query,
                "tags": "comment",
                "hitsPerPage": work.command.limit,
                "page": 0,
            },
            timeout=httpx.Timeout(15, connect=5),
            follow_redirects=False,
        ) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ValueError("Source response exceeds 2 MB limit")
        data = SearchResponse.model_validate_json(body)
        if len(data.hits) > work.command.limit:
            raise ValueError("Source returned more items than requested")
        captured_at = datetime.now(UTC)
        materials = []
        skipped = 0
        for hit in data.hits:
            quote = comment_text(hit.comment_text or "")
            if not quote or quote in {"[deleted]", "[dead]"}:
                skipped += 1
                continue
            materials.append(
                SourceMaterial(
                    url=f"https://news.ycombinator.com/item?id={hit.objectID}",
                    external_id=hit.objectID,
                    title=hit.story_title[:300] if hit.story_title else None,
                    captured_at=captured_at,
                    quote=quote,
                    metadata={
                        "author": hit.author,
                        "published_at": hit.created_at.isoformat() if hit.created_at else None,
                        "story_url": hit.story_url,
                        "story_title": hit.story_title,
                        "raw_comment_html": hit.comment_text,
                        "query": work.command.query,
                        "adapter": "hacker-news-comments-v1",
                    },
                )
            )
        # Empty material is an explicit valid result, never invented evidence.
        return ResearchResult(
            hypothesis_version_id=work.version.id, materials=materials, skipped_items=skipped
        )
