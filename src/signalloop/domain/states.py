from enum import StrEnum


class State(StrEnum):
    DRAFT = "DRAFT"
    FEASIBILITY = "FEASIBILITY"
    RESEARCH = "RESEARCH"
    READY_FOR_EXPERIMENT = "READY_FOR_EXPERIMENT"
    EXPERIMENT = "EXPERIMENT"
    EVALUATION = "EVALUATION"
    ITERATION = "ITERATION"
    PAUSED = "PAUSED"
    REJECTED = "REJECTED"
    VALIDATED = "VALIDATED"


TRANSITIONS: dict[State, frozenset[State]] = {
    State.DRAFT: frozenset({State.FEASIBILITY}),
    State.FEASIBILITY: frozenset({State.RESEARCH, State.PAUSED, State.REJECTED}),
    State.RESEARCH: frozenset(
        {State.READY_FOR_EXPERIMENT, State.ITERATION, State.PAUSED, State.REJECTED}
    ),
    State.READY_FOR_EXPERIMENT: frozenset({State.EXPERIMENT}),
    State.EXPERIMENT: frozenset({State.EVALUATION}),
    State.EVALUATION: frozenset({State.VALIDATED, State.ITERATION, State.PAUSED, State.REJECTED}),
    State.ITERATION: frozenset({State.RESEARCH}),
    State.PAUSED: frozenset(),
    State.REJECTED: frozenset(),
    State.VALIDATED: frozenset(),
}


class DomainError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def validate_transition(current: State, target: State) -> None:
    if target not in TRANSITIONS[current]:
        raise DomainError(f"Invalid transition: {current} -> {target}")


class ActorType(StrEnum):
    human = "human"
    agent = "agent"
    system = "system"


class Stance(StrEnum):
    supports = "supports"
    contradicts = "contradicts"
    neutral = "neutral"
    unknown = "unknown"


class Decision(StrEnum):
    continue_ = "continue"
    iterate = "iterate"
    pause = "pause"
    reject = "reject"
    validate = "validate"


DECISION_TARGETS = {
    Decision.iterate: State.ITERATION,
    Decision.pause: State.PAUSED,
    Decision.reject: State.REJECTED,
    Decision.validate: State.VALIDATED,
}


class ReviewDecision(StrEnum):
    approved = "approved"
    rejected = "rejected"
    modified = "modified"
    escalated = "escalated"


class ExperimentStatus(StrEnum):
    planned = "planned"
    running = "running"
    completed = "completed"
    cancelled = "cancelled"


class RunStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
