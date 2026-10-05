# SignalLoop

SignalLoop preserves what we believed, what we observed, what we tested, and why we changed direction while validating product and business ideas. PostgreSQL is its durable memory; future AI workers contribute traceable research and interpretations without replacing deterministic application rules.

Foundation v0.1 is a domain-independent API for manually operating this loop. Camper / Vanlife / Overlanding is its first example vertical. All example product claims and prices are assumptions, not validated facts.

## What Foundation v0.1 provides

- Hypotheses with immutable, numbered versions and a current-version pointer.
- Centrally validated state transitions and append-only history.
- Manually entered sources, evidence, experiments, observed signals and decisions.
- Provider-neutral agent-run traces and human reviews, without running agents.
- Relational decision support links and provenance (`human`, `agent`, `system`).
- FastAPI OpenAPI, PostgreSQL migrations, Docker Compose and integration tests.

An assumption belongs in a hypothesis version. Evidence captures sourced information. A signal records an observed action or feedback event. An interpretation is an analysis, not a market event. A decision records what to do and why. No integrations, LLM calls, authentication or frontend are included.

## Start locally

Requires Docker Engine and the Docker Compose plugin:

```bash
cp .env.example .env
docker compose up --build
```

Open [Swagger UI](http://localhost:8000/docs), [OpenAPI JSON](http://localhost:8000/openapi.json), or [health](http://localhost:8000/health). The API waits for PostgreSQL and applies Alembic migrations before starting. Data persists in the `postgres_data` named volume. Ports bind to localhost; the example password is for local development only.

Run the complete example using Python 3.12+ (no packages needed):

```bash
python scripts/manual_loop.py
```

This creates a **simulated** camper-storage hypothesis, v1 at €449, a source and evidence, an experiment and three signals, an iteration decision, and v2 at €349. It verifies v1 is unchanged and ends in `RESEARCH`. Repeating it creates another independent example. The quote and events are explicitly labelled simulated and must not be treated as real validation.

```bash
docker compose --profile test run --build --rm test
docker compose down
```

Tests create and remove random isolated PostgreSQL schemas; they do not clear application data. `down` keeps the database volume. Do not use `down -v` unless you intend to destroy local data.

## Repository map

```text
src/signalloop/
  api/app.py              HTTP adapters, OpenAPI, error mapping
  domain/states.py         States, transitions, domain errors and enums
  models/entities.py       SQLAlchemy relational mappings
  schemas/contracts.py    Pydantic input/output contracts
  repositories/store.py   Common persistence queries and row locking
  services/backbone.py    Transactional domain operations
  db/session.py           Configuration, engine and transaction scope
alembic/                  Versioned schema and append-only guards
scripts/manual_loop.py    Executable acceptance scenario
tests/                   PostgreSQL behavior and migration tests
docs/                     Design docs and original architecture PDFs
```

## API overview

All create endpoints return `201`. Lists accept `limit` (1–200, default 100) and `offset` (default 0). UUIDs identify records; the version path uses an integer version number.

| Resource | Endpoints |
|---|---|
| Health | `GET /health` (checks the database) |
| Hypotheses | `POST, GET /hypotheses`; `GET /hypotheses/{id}` |
| Versions | `POST, GET /hypotheses/{id}/versions`; `GET /hypotheses/{id}/versions/{version_no}` |
| State | `POST /hypotheses/{id}/transition`; `GET /hypotheses/{id}/history` |
| Sources | `POST, GET /sources`; `GET /sources/{id}` |
| Evidence | `POST, GET /hypotheses/{id}/evidence`; `GET /evidence/{id}` |
| Experiments | `POST, GET /hypotheses/{id}/experiments`; `GET /experiments/{id}` |
| Signals | `POST, GET /experiments/{id}/signals` |
| Decisions | `POST, GET /hypotheses/{id}/decisions` |
| Agent runs | `POST, GET /agent-runs`; `GET /agent-runs/{id}` |
| Human reviews | `POST, GET /human-reviews`; `GET /human-reviews/{id}` |

Swagger documents exact request/response fields. Missing records return `404`, invalid input or cross-hypothesis references `422`, invalid transitions and database integrity conflicts `409`, and unavailable PostgreSQL `503`. Unknown request fields are rejected. No PATCH or DELETE endpoints are provided.

Create a hypothesis and v1 in one transaction:

```json
{
  "title": "Removable Modular Rear Storage System",
  "domain": "Camper / Vanlife / Overlanding",
  "created_by": "mario",
  "version": {
    "target_customer": "Ducato / Jumper / Boxer camper and dual-use owners",
    "problem": "Existing organised storage solutions often require permanent installation.",
    "offer": "Removable modular rear storage system.",
    "price_assumption": "449.00",
    "currency": "EUR",
    "success_criteria": "Validate demand and willingness to pay.",
    "change_reason": "Initial unvalidated assumptions",
    "created_by": "mario"
  }
}
```

Version fields are full snapshots, not patches. Evidence and experiment creation default to the current version, or accept an explicit `hypothesis_version_id`. Earlier-version records remain accessible after iteration.

Decisions use lowercase values (`continue`, `iterate`, `pause`, `reject`, `validate`). State values are uppercase. State-changing decisions atomically perform the corresponding valid transition; `continue` records rationale without changing state. Supply `originating_decision_id` when creating a later version to preserve the iteration link.

## Review and live demonstration

See the [review briefing](docs/foundation-review.md) for a 12-minute walkthrough, live inspection links, current results and limitations. Run `python scripts/review_demo.py --pause` for the narrated API demonstration. All generated business observations are simulated.

## Design and development

- [Architecture and scope](docs/architecture.md)
- [Domain model and invariants](docs/domain-model.md)
- [State machine and decision semantics](docs/state-machine.md)
- [Install, migrate, test, lint and format](docs/development.md)
- Original references: [database architecture](docs/hypothesis_loop_database_architecture.pdf) and [system interaction](docs/hypothesis_loop_system_interaction.pdf). The Foundation v0.1 task takes precedence over their milestone recommendations.

## Deliberate limitations and next milestone

This is a local prototype, not a public service. Reviewer and producer identifiers are asserted, not authenticated. Human reviews persist approvals but do not dispatch actions. AgentRun endpoints store submitted snapshots; lifecycle updates, retries, idempotency and scheduling await an actual worker. Experiment creation stores a plan or manually supplied result snapshot; hypothesis transitions do not automatically start or complete experiments. Signal content relies on honest reporting of observations, not automatic truth verification.

The supplied state graph has no outgoing transitions from `PAUSED`, `REJECTED` or `VALIDATED`. Success criteria are explanatory text; automated evaluation and structured metric definitions are deferred. There is no dashboard, count aggregation, integration, crawling, prospecting or outreach. Business operations must go through services, rather than direct SQL status updates.

Recommended next milestone: one narrowly scoped Research Worker for one deliberately selected source/channel, using validated inputs/outputs, recording AgentRun provenance, Source and Evidence, with explicit retry/idempotency and human review semantics. It is **not** implemented here.
