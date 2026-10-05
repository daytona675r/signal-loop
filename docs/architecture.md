# Architecture

SignalLoop Foundation v0.1 is a deterministic, domain-independent application with PostgreSQL as durable memory. Its first example vertical is camper/vanlife/overlanding; core code has no vehicle or camper-specific fields.

```text
Future Dashboard / Workers / Agents
               │
               ▼
            FastAPI
               │
               ▼
       Application Services
               │
               ▼
          Repositories
               │
               ▼
          PostgreSQL
```

HTTP handlers validate typed contracts and delegate mutations to `Backbone`. Services own domain decisions and compose queries; `Store` contains common persistence and row-lock operations. SQLAlchemy's Session already supplies a unit of work, so no additional repository interfaces or transaction framework are needed. Straightforward relation-specific queries remain in the service rather than becoming one-line repository wrappers.

A request gets one transaction, committed **before** its response is sent. Exceptions roll it back. Services also work in an explicitly opened Session transaction outside HTTP. Workers will run as separate processes beside the API, either calling it or reusing services; they will not execute inside request handlers.

## Durability and concurrency

- Creating a hypothesis, v1 and initial `DRAFT` history is atomic.
- Creating a version locks the hypothesis, allocates the next number, writes a snapshot and changes the current pointer atomically. Concurrent callers produce distinct consecutive versions.
- Transitions lock the same row, validate against the single domain transition map and append history in one transaction. A competing duplicate transition fails.
- State-changing decisions validate first, then persist the decision, support links, status and history together.
- A deferred composite foreign key makes the circular hypothesis/current-version relationship valid at commit while rejecting cross-hypothesis pointers.
- Database triggers reject UPDATE/DELETE of versions and historical records. These are storage integrity guards, not workflow or agent logic. Migration operations may remove them deliberately; a privileged database owner can bypass protections, so this is not a tamper-proof ledger.
- Foreign keys use restrictive semantics; no destructive API or cascade deletion of audit history is exposed.

## Reference documents and scope resolutions

Both architecture PDFs are retained verbatim in this folder. The database PDF defers Experiments and Signals from its minimal slice; the user’s Foundation prompt explicitly includes them. The interaction PDF proposes a first research worker and broader orchestration packages; these are deferred by the prompt. Prospect, Outreach and Channel tables are not implemented.

The PDF says evidence always references a source; the prompt explicitly permits an optional Source. Source-less evidence still records creator and timestamp. Versions are immutable immediately, a stronger and simpler invariant than freezing them only when testing starts.

The prompt's acceptance scenario records `ITERATE` and later assumes `ITERATION`, without explicitly transitioning there. Foundation resolves this by making state-changing decisions call the same transition service atomically. `continue` does not infer a new state. `to_version_id` refers only to an existing version; a later version points back through `originating_decision_id`, preserving the earlier decision without mutation.

## Choices affecting future workers

Pydantic schemas form explicit input/output contracts. JSONB holds external metadata, structured facts, snapshots and raw events. IDs, states, prices, version relationships, approval targets and decision support are relational.

AgentRun is provider-neutral and can be referenced by produced records. Its input/output snapshots may contain interpretations; those are never automatically converted into Signals. A future evaluation worker should store a proposed decision in its run output for review; the Decision API records **effective** decisions and may change state. It must not be used as an unapproved proposal inbox.

HumanReview uses one of four explicit FK targets (version, experiment, decision, run). Adding future reviewable entities requires a migration and contract change, intentionally preserving relationship integrity rather than adopting a dangling polymorphic object ID. A modified review records notes; it does not mutate the target or perform an external action.

Version and experiment success criteria are plain explanatory text. Future automated metrics should add explicit typed fields/tables through migrations. Channel names and signal/source types remain extensible strings. Adding a new hypothesis state requires changing the enum, transition map and database check constraints in a migration.

Sources, evidence, signals, reviews and decisions are append-only. Corrections currently require an explanatory new record; formal supersedes/retraction relationships are a later design decision. Versions can be created in any state; existing experiments always retain their original version reference. No hidden workflow prerequisites (evidence count, experiment count or approval gates) have been invented.

This release has no authentication, worker scheduling, LLM integration, idempotency mechanism, automated experiment execution or production deployment infrastructure.
