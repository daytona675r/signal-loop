from sqlalchemy import select
from sqlalchemy.orm import Session

from signalloop.domain.states import DomainError
from signalloop.models.entities import Hypothesis


class Store:
    """Small shared queries; transaction ownership belongs to the caller."""

    def __init__(self, session: Session):
        self.session = session

    def require(self, model, identifier):
        row = self.session.get(model, identifier)
        if row is None:
            raise DomainError(f"{model.__name__} not found", 404)
        return row

    def lock_hypothesis(self, identifier):
        row = self.session.scalar(
            select(Hypothesis)
            .where(Hypothesis.id == identifier)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise DomainError("Hypothesis not found", 404)
        return row

    def add(self, row):
        self.session.add(row)
        self.session.flush()
        return row

    def list(self, model, *criteria, limit=100, offset=0):
        statement = select(model).where(*criteria).order_by(model.created_at, model.id)
        return list(self.session.scalars(statement.limit(limit).offset(offset)))
