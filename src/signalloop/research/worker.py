"""Synchronous application entrypoint, callable outside the HTTP process."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from signalloop.domain.states import DomainError
from signalloop.models.entities import HypothesisVersion
from signalloop.repositories.store import Store
from signalloop.research.contracts import ResearchCommand, ResearchInput, ResearchResult
from signalloop.schemas.contracts import VersionRead


class ResearchWorker:
    def __init__(
        self,
        sessions: Callable[[], Session],
        collect: Callable[[ResearchInput], ResearchResult],
    ):
        self.sessions = sessions
        self.collect = collect

    def run(self, command: ResearchCommand) -> ResearchResult:
        with self.sessions() as session:
            version = Store(session).require(HypothesisVersion, command.hypothesis_version_id)
            work = ResearchInput(command=command, version=VersionRead.model_validate(version))
        result = ResearchResult.model_validate(self.collect(work))
        if result.hypothesis_version_id != command.hypothesis_version_id:
            raise DomainError("Research output references a different version", 422)
        if len(result.materials) > command.limit:
            raise DomainError("Research output exceeds the requested limit", 422)
        return result
