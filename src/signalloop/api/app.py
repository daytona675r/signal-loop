from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from signalloop.db.session import get_session
from signalloop.domain.states import DomainError
from signalloop.models import entities as m
from signalloop.schemas import contracts as c
from signalloop.services.backbone import Backbone

app = FastAPI(
    title="SignalLoop",
    version="0.1.0",
    description="Manual hypothesis validation. Assumptions, evidence, observations and decisions "
    "remain distinct. No autonomous execution or authentication.",
)
Database = Annotated[Session, Depends(get_session)]


def service(session: Database):
    return Backbone(session)


Service = Annotated[Backbone, Depends(service)]


def pagination(
    limit: Annotated[int, Query(ge=1, le=200)] = 100, offset: Annotated[int, Query(ge=0)] = 0
):
    return {"limit": limit, "offset": offset}


Page = Annotated[dict, Depends(pagination)]


@app.exception_handler(DomainError)
async def domain_error(request: Request, exc: DomainError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(IntegrityError)
async def integrity_error(request: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=409, content={"detail": "Database integrity constraint violated"}
    )


@app.exception_handler(OperationalError)
async def database_error(request: Request, exc: OperationalError):
    return JSONResponse(status_code=503, content={"detail": "Database temporarily unavailable"})


@app.get("/health", response_model=c.HealthRead, tags=["Health"])
def health(session: Database):
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/hypotheses", response_model=c.HypothesisRead, status_code=201, tags=["Hypotheses"])
def create_hypothesis(payload: c.HypothesisCreate, svc: Service):
    return svc.create_hypothesis(payload)


@app.get("/hypotheses", response_model=list[c.HypothesisRead], tags=["Hypotheses"])
def hypotheses(svc: Service, page: Page):
    return svc.store.list(m.Hypothesis, **page)


@app.get("/hypotheses/{hypothesis_id}", response_model=c.HypothesisRead, tags=["Hypotheses"])
def hypothesis(hypothesis_id: UUID, svc: Service):
    return svc.store.require(m.Hypothesis, hypothesis_id)


@app.get(
    "/hypotheses/{hypothesis_id}/versions", response_model=list[c.VersionRead], tags=["Versions"]
)
def versions(hypothesis_id: UUID, svc: Service, page: Page):
    return svc.versions(hypothesis_id, **page)


@app.get(
    "/hypotheses/{hypothesis_id}/versions/{version_no}",
    response_model=c.VersionRead,
    tags=["Versions"],
)
def version(hypothesis_id: UUID, version_no: int, svc: Service):
    return svc.get_version(hypothesis_id, version_no)


@app.post(
    "/hypotheses/{hypothesis_id}/versions",
    response_model=c.VersionRead,
    status_code=201,
    tags=["Versions"],
)
def create_version(hypothesis_id: UUID, payload: c.VersionCreate, svc: Service):
    return svc.create_version(hypothesis_id, payload)


@app.post(
    "/hypotheses/{hypothesis_id}/transition",
    response_model=c.HistoryRead,
    status_code=201,
    tags=["State"],
)
def transition(hypothesis_id: UUID, payload: c.TransitionCreate, svc: Service):
    return svc.transition(hypothesis_id, payload)


@app.get("/hypotheses/{hypothesis_id}/history", response_model=list[c.HistoryRead], tags=["State"])
def history(hypothesis_id: UUID, svc: Service, page: Page):
    return svc.history(hypothesis_id, **page)


@app.post("/sources", response_model=c.SourceRead, status_code=201, tags=["Sources"])
def create_source(payload: c.SourceCreate, svc: Service):
    return svc.create_source(payload)


@app.get("/sources", response_model=list[c.SourceRead], tags=["Sources"])
def sources(svc: Service, page: Page):
    return svc.store.list(m.Source, **page)


@app.get("/sources/{source_id}", response_model=c.SourceRead, tags=["Sources"])
def source(source_id: UUID, svc: Service):
    return svc.store.require(m.Source, source_id)


@app.post(
    "/hypotheses/{hypothesis_id}/evidence",
    response_model=c.EvidenceRead,
    status_code=201,
    tags=["Evidence"],
)
def create_evidence(hypothesis_id: UUID, payload: c.EvidenceCreate, svc: Service):
    return svc.create_evidence(hypothesis_id, payload)


@app.get(
    "/hypotheses/{hypothesis_id}/evidence", response_model=list[c.EvidenceRead], tags=["Evidence"]
)
def evidence(hypothesis_id: UUID, svc: Service, page: Page):
    return svc.version_records(m.Evidence, hypothesis_id, **page)


@app.get("/evidence/{evidence_id}", response_model=c.EvidenceRead, tags=["Evidence"])
def evidence_record(evidence_id: UUID, svc: Service):
    return svc.store.require(m.Evidence, evidence_id)


@app.post(
    "/hypotheses/{hypothesis_id}/experiments",
    response_model=c.ExperimentRead,
    status_code=201,
    tags=["Experiments"],
)
def create_experiment(hypothesis_id: UUID, payload: c.ExperimentCreate, svc: Service):
    return svc.create_experiment(hypothesis_id, payload)


@app.get(
    "/hypotheses/{hypothesis_id}/experiments",
    response_model=list[c.ExperimentRead],
    tags=["Experiments"],
)
def experiments(hypothesis_id: UUID, svc: Service, page: Page):
    return svc.version_records(m.Experiment, hypothesis_id, **page)


@app.get("/experiments/{experiment_id}", response_model=c.ExperimentRead, tags=["Experiments"])
def experiment(experiment_id: UUID, svc: Service):
    return svc.store.require(m.Experiment, experiment_id)


@app.post(
    "/experiments/{experiment_id}/signals",
    response_model=c.SignalRead,
    status_code=201,
    tags=["Signals"],
)
def create_signal(experiment_id: UUID, payload: c.SignalCreate, svc: Service):
    return svc.create_signal(experiment_id, payload)


@app.get(
    "/experiments/{experiment_id}/signals", response_model=list[c.SignalRead], tags=["Signals"]
)
def signals(experiment_id: UUID, svc: Service, page: Page):
    return svc.signals(experiment_id, **page)


@app.post(
    "/hypotheses/{hypothesis_id}/decisions",
    response_model=c.DecisionRead,
    status_code=201,
    tags=["Decisions"],
)
def create_decision(hypothesis_id: UUID, payload: c.DecisionCreate, svc: Service):
    return svc.create_decision(hypothesis_id, payload)


@app.get(
    "/hypotheses/{hypothesis_id}/decisions", response_model=list[c.DecisionRead], tags=["Decisions"]
)
def decisions(hypothesis_id: UUID, svc: Service, page: Page):
    return svc.decisions(hypothesis_id, **page)


@app.post("/agent-runs", response_model=c.AgentRunRead, status_code=201, tags=["Agent runs"])
def create_agent_run(payload: c.AgentRunCreate, svc: Service):
    return svc.create_agent_run(payload)


@app.get("/agent-runs", response_model=list[c.AgentRunRead], tags=["Agent runs"])
def agent_runs(svc: Service, page: Page):
    return svc.store.list(m.AgentRun, **page)


@app.get("/agent-runs/{run_id}", response_model=c.AgentRunRead, tags=["Agent runs"])
def agent_run(run_id: UUID, svc: Service):
    return svc.store.require(m.AgentRun, run_id)


@app.post(
    "/human-reviews", response_model=c.HumanReviewRead, status_code=201, tags=["Human reviews"]
)
def create_review(payload: c.HumanReviewCreate, svc: Service):
    return svc.create_review(payload)


@app.get("/human-reviews", response_model=list[c.HumanReviewRead], tags=["Human reviews"])
def reviews(svc: Service, page: Page):
    return svc.store.list(m.HumanReview, **page)


@app.get("/human-reviews/{review_id}", response_model=c.HumanReviewRead, tags=["Human reviews"])
def review(review_id: UUID, svc: Service):
    return svc.store.require(m.HumanReview, review_id)
