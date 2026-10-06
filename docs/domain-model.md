# Domain model

## Semantic boundaries

| Concept | Meaning | Example |
|---|---|---|
| Assumption | A belief to test, stored in a version | Customers dislike permanent installation; €449 may be viable |
| Evidence | Concrete information, optionally linked to a source | “I don't want to drill holes into my van.” |
| Signal | Observed interaction or feedback, linked to an experiment | An email submission or a price objection |
| Interpretation | Analysis of evidence/signals, not an observed event | No-drill installation may matter; store in an AgentRun output or review notes |
| Decision | Explicit next step with rationale and supporting references | Iterate to test price sensitivity |

The example quote and events in tests and the manual script are simulated. The system cannot determine whether a caller is truthful; its contracts preserve semantic boundaries without pretending to verify market reality.

## Tables

All entity IDs use PostgreSQL UUIDs. Entity `created_at` fields and event timestamps are timezone-aware. Pydantic rejects naive input timestamps. Prices use `NUMERIC(12,2)` and a separate three-letter uppercase currency; serialized decimals are strings to avoid binary floating-point loss.

| Table | Responsibility and important relationships |
|---|---|
| `hypothesis` | Stable identity, title, domain, status, current version, timestamps and provenance |
| `hypothesis_version` | Immutable snapshot: target customer, problem, offer, price/currency, criteria, change reason; FK to hypothesis; optional originating decision |
| `source` | Captured provenance: URL, platform, type, title, external ID, hash, captured time, flexible metadata |
| `evidence` | FK to version and optional source; stance, strength, quote/summary, structured facts, producer/run |
| `experiment` | FK to tested version; name, objective, channel, offer variant, price, criteria, status, schedule and manual result summary |
| `signal` | FK to experiment; type, numeric value, optional strength, observation text, occurred time and raw payload |
| `agent_run` | Role, run type, provider/model/prompt version, input/output snapshots, trace ID, cost/currency, latency in milliseconds, status, errors and timings |
| `human_review` | Exactly one FK target: version, experiment, decision or agent run; decision, notes, reviewer and review time |
| `decision_log` | FK to hypothesis and same-hypothesis from/to versions; decision, rationale and provenance |
| `transition_history` | FK to hypothesis and version; per-hypothesis sequence, previous/next state, reason, optional decision, timestamp and actor |
| `decision_evidence` | Relational many-to-many support links |
| `decision_signal` | Relational many-to-many support links |

## Invariants

- Version numbers are positive and unique per hypothesis. The current-version composite FK proves ownership; it is non-null and deferred during creation.
- From/to decision versions and originating decisions must belong to the same hypothesis (composite database FKs). Supporting evidence/signals must belong to that hypothesis (service validation). Cross-version support within a hypothesis is allowed.
- Version 2 is a full snapshot, never a patch to v1. Its optional originating decision supplies a historically accurate forward link, exposed as `resulting_version_ids` when reading decisions.
- History includes an initial `NULL → DRAFT` row. Later transitions retain their contemporaneous version ID even after the current pointer changes.
- Valid evidence stances: `supports`, `contradicts`, `neutral`, `unknown`. Optional strength is a declared 0–1 score, not a market observation or a probability of success.
- Signals require an observation and timezone-aware event time. An agent may report an externally observed event; producer type alone cannot establish that the content is a real signal.
- Experiment statuses: `planned`, `running`, `completed`, `cancelled`. They are independent of the hypothesis state. No automatic experiment lifecycle is implemented.
- Agent statuses: `pending`, `running`, `succeeded`, `failed`. These endpoints persist snapshots, with no execution or lifecycle mutation yet. Costs and latency are nonnegative.
- Human review decisions: `approved`, `rejected`, `modified`, `escalated`. Exactly one review target is required in the API and by a database constraint. Notes on a modification explain the change; they do not rewrite snapshots.
- Most produced records include `created_by_type`, `created_by`, and optional FK `agent_run_id`. Actor IDs are unauthenticated caller assertions. Both the stable hypothesis and its nested initial version carry explicit provenance; defaults are `human`/`manual`.
- Source, evidence, signal, version, decision, support links, history and review records reject updates/deletes at database level. Other models have no API mutation endpoints, but no append-only database trigger.
- Relationship columns have indexes, alongside hypothesis status/domain, source type/hash, signal type and agent trace ID. List endpoints paginate; no large-scale query optimizations are assumed.

## Flexible data

JSONB is limited to Source metadata, Evidence structured facts, Signal raw payload, and AgentRun input/output snapshots. Criteria, prices, states and relationships remain normal columns. URLs are optional (interviews/manual observations may have none); supplied URLs must use HTTP(S). Source hashes/external IDs are not globally unique: recaptures and platform scopes may differ.

No Prospect, Outreach, Channel, vector store, embedding, or interpretation subsystem is implemented. Add those deliberately when a real worker or experiment needs them.

## Originating decision validation

A supplied `originating_decision_id` must identify an `iterate` decision of the same hypothesis whose `from_version_id` is the current version. The hypothesis must still be in `ITERATION`, and that decision must be the one attached to the latest transition into this iteration. An older decision cannot be reused after returning to research and entering a later iteration, even if the version has not changed. Non-iteration decisions and already-consumed origins are rejected with `422` before inserting a version or moving the current pointer.

The origin remains optional: manually creating a version without a decision link is still allowed. A missing decision ID returns `404`. No schema migration or rewriting of existing historical links is performed.
