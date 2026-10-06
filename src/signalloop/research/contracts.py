"""Narrow, version-specific research contracts; no implicit current-version lookup."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, HttpUrl
from pydantic.types import AwareDatetime

from signalloop.schemas.contracts import Contract, Short, Text, VersionRead


class ResearchCommand(Contract):
    hypothesis_version_id: UUID
    query: Short
    limit: Annotated[int, Field(ge=1, le=20)] = 5


class ResearchInput(Contract):
    command: ResearchCommand
    version: VersionRead


class SourceMaterial(Contract):
    url: HttpUrl
    external_id: Annotated[str, Field(min_length=1, max_length=300)]
    title: Annotated[str, Field(min_length=1, max_length=300)] | None = None
    captured_at: AwareDatetime
    quote: Text
    metadata: dict = Field(default_factory=dict)


class ResearchResult(Contract):
    agent_run_id: UUID | None = None
    hypothesis_version_id: UUID
    source_type: Literal["hacker_news_comment"] = "hacker_news_comment"
    skipped_items: Annotated[int, Field(ge=0)] = 0
    materials: list[SourceMaterial] = Field(default_factory=list, max_length=20)
