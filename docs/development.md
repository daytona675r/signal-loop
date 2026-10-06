# Local development

## Requirements and configuration

Docker Engine + Docker Compose are enough to run API, PostgreSQL and container tests. Native development requires Python 3.12+ and PostgreSQL (the Compose database is convenient).

```bash
cp .env.example .env
docker compose up --build
```

Swagger: http://localhost:8000/docs. Health: http://localhost:8000/health. PostgreSQL: localhost:5433. `API_PORT` and `DB_PORT` can be overridden in `.env`; update native `DATABASE_URL` if you change the database port. Compose constructs its internal connection URL using the PostgreSQL settings and hostname `db`; native tools read `DATABASE_URL`. For local custom credentials avoid URL-reserved password characters, or provide a properly percent-encoded connection URL via a Compose override.

Only loopback ports are published. Default credentials are explicitly local examples; `.env` is ignored by Git and Docker. No real secrets belong in committed files. Password/database environment changes do not reconfigure an existing PostgreSQL volume; use SQL administration or a deliberately new development volume.

## Native install and start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
docker compose up -d db
alembic upgrade head
uvicorn signalloop.api.app:app --reload
```

Stop the container API first if using the same host port: `docker compose stop api`.

Dependencies have compatible version bounds in `pyproject.toml`; a frozen production dependency lock and deployment hardening are deferred. The Docker image uses Python 3.12 and runs the API as a non-root user.

## Start and stop

```bash
docker compose up -d --build
docker compose logs -f api
docker compose stop
docker compose start
docker compose down
```

`down` removes the containers/network but preserves data. `docker compose down -v` deletes the data volume and is destructive. Application shutdown/startup never resets the database.

## Migrations

```bash
# Native, with the virtual environment active:
alembic upgrade head
alembic current
alembic check
alembic revision --autogenerate -m 'describe schema change'

# Container alternative:
docker compose exec api alembic upgrade head
docker compose exec api alembic current
```

Create migrations on the host so generated files stay in the repository. Review autogeneration: cyclic foreign keys, enum/check changes, and triggers need explicit handling. Initial revision `c3cba3b019c6` creates the 12 tables and constraints, adding FKs after tables to resolve cycles. `0002` adds append-only guards. `0003` adds per-hypothesis history sequence numbers, including a transactional backfill for existing rows. Migrations are frozen snapshots and never import current application models. `alembic/env.py` imports models for autogeneration/drift checks only.

Tests verify upgrade from an empty schema, model drift, downgrade to base and upgrade again inside a disposable schema. Downgrades destroy data; use them only in disposable development environments. API startup runs `alembic upgrade head`, which is suitable for a single local API container; multi-replica production startup would need a separate coordinated migration step.

## Tests

```bash
docker compose --profile test run --build --rm test

# Native alternative:
export TEST_DATABASE_URL=postgresql+psycopg://signalloop:local-development-only@localhost:5433/signalloop
pytest -q
```

Tests require real PostgreSQL; there is no SQLite fallback. `TEST_DATABASE_URL` must be explicit for native tests. The database user needs CREATE SCHEMA permission. Fixtures create uniquely named schemas, migrate them and drop only those schemas when finished. API transactions actually commit, so tests can detect deferred FK violations and exercise concurrent writers. Interrupting tests abruptly can leave an isolated `test_signalloop_*` schema for later cleanup.

Coverage includes the full acceptance loop, all specified branch transitions, terminal-state behavior, immutable historical versions, source/evidence/experiment/signal creation and reads, decision support links, reviews/run provenance, validation, missing relationships, cross-hypothesis rejection, rollback, concurrent version creation, competing transitions, database constraints and migration round trips.

## Manual acceptance scenario

```bash
python scripts/manual_loop.py
# If using another port:
python scripts/manual_loop.py --base-url http://localhost:8001
```

This uses only Python's standard library and exercises the **running HTTP server**, not in-process test overrides. Each run creates a fresh clearly labelled simulated hypothesis. It verifies v1 (€449) remains unchanged, v2 (€349) references the iteration decision, and the final state is `RESEARCH` with eight history records. It never publishes a landing page or contacts a customer.

## Lint and format

```bash
ruff check .
ruff format --check .
ruff format .
```

Run tests and lint before a checkpoint. Work on `foundation-v0.2`; push that branch without force-pushing, merging into main or rewriting history. Both architecture PDFs remain in `docs/` as reference material.

## Calling services from a future worker

```python
from sqlalchemy.orm import Session
from signalloop.db.session import get_engine
from signalloop.schemas.contracts import SourceCreate
from signalloop.services.backbone import Backbone

with Session(get_engine()) as session, session.begin():
    source = Backbone(session).create_source(
        SourceCreate(
            source_type="manual_observation",
            title="A deliberately supplied observation",
            created_by_type="system",
            created_by="example-importer",
        )
    )
```

Future workers receive version IDs and narrow typed inputs, return validated outputs and store run provenance. They must not directly mutate versions or status fields, keep durable state in conversation history, or use Signals for LLM conclusions. Retry policies, deduplication keys, run lifecycle updates and proposal approvals need design before running a real worker.

## GitHub Actions quality gate

`.github/workflows/foundation.yml` runs on pushes to `foundation-v0.1`/`foundation-v0.2` and pull requests targeting either branch. One Ubuntu job uses Python 3.12, installs the existing `.[dev]` dependencies, builds the application's `base` Docker target through `docker compose build api`, runs both Ruff checks, and starts the existing Compose PostgreSQL service. It then applies migrations, checks Alembic drift, and runs the full PostgreSQL-backed pytest suite with its isolated schemas.

Every check uses normal failing exit codes; there is no `continue-on-error`. A failure fails the job and later dependent checks are skipped. An always-run GitHub job summary records build, Ruff, database, migration and test outcomes with the tested commit SHA (the merge commit for PR runs). Failure diagnostics include PostgreSQL logs. Runner-local containers and volumes are removed afterward; this cleanup does not touch a developer's database. Superseded runs on the same ref are cancelled.

The workflow uses read-only repository permissions and introduces no deployment, registry publishing or external application services. Package and image downloads remain necessary for installation/builds. This supplies a visible CI status check; making it a required merge check through branch protection is a separate repository setting.


## Foundation v0.2 worker

See [research-worker.md](research-worker.md). Migration `0004` adds the optional relational AgentRun version link. The CLI runs synchronously beside the HTTP server, not in a request handler. The full pytest suite automatically includes v0.2 acceptance/failure tests; all v0.1 test files are retained unchanged.

```bash
docker compose up -d --build
python scripts/research_demo.py
```

The demo uses the running API plus a separate CLI process inside the API image. It makes one real source request and leaves the completed result awaiting explicit human review. `python scripts/manual_loop.py` and `python scripts/review_demo.py` still demonstrate the accepted v0.1 behavior using simulated events.
