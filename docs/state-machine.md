# State machine

The single transition map is `src/signalloop/domain/states.py`. Services validate it while holding a PostgreSQL row lock; routes do not implement state rules. Invalid transitions, including a repeat of the current state, return `409` without changing status or history.

| Current state | Allowed next states |
|---|---|
| DRAFT | FEASIBILITY |
| FEASIBILITY | RESEARCH, PAUSED, REJECTED |
| RESEARCH | READY_FOR_EXPERIMENT, ITERATION, PAUSED, REJECTED |
| READY_FOR_EXPERIMENT | EXPERIMENT |
| EXPERIMENT | EVALUATION |
| EVALUATION | VALIDATED, ITERATION, PAUSED, REJECTED |
| ITERATION | RESEARCH |
| PAUSED | None in v0.1 |
| REJECTED | None in v0.1 |
| VALIDATED | None in v0.1 |

```http
POST /hypotheses/{id}/transition
Content-Type: application/json

{
  "target_state": "RESEARCH",
  "reason": "Initial feasibility assumptions look plausible.",
  "created_by_type": "human",
  "created_by": "mario"
}
```

The example succeeds only from `FEASIBILITY` or `ITERATION`. Status and history commit together. A per-hypothesis sequence number allocated under the same row lock orders history even when multiple transitions share a timestamp. History can be queried through `GET /hypotheses/{id}/history` and contains old/new states, the current version at the time, reason, actor, optional AgentRun and optional DecisionLog.

## Decision effects

| Decision value | Effect |
|---|---|
| `continue` | Persist rationale; no inferred transition |
| `iterate` | Transition to ITERATION |
| `pause` | Transition to PAUSED |
| `reject` | Transition to REJECTED |
| `validate` | Transition to VALIDATED |

All state-changing decisions obey the same map and must refer to the current version. If the target is not allowed, neither the decision nor its support links are persisted. Historical `continue` decisions can refer to older versions. State changes are independent of experiment status and do not dispatch work.

The acceptance loop is:

```text
create v1 + DRAFT
→ FEASIBILITY → RESEARCH
→ add source/evidence
→ READY_FOR_EXPERIMENT → create experiment
→ EXPERIMENT → add simulated signals
→ EVALUATION → decision iterate (atomically enters ITERATION)
→ create v2, linked to the decision
→ RESEARCH
```

A new version changes the current pointer, not the state. The graph intentionally has no pause/resume rule because none was specified. Adding one later requires a deliberate policy decision and tests. New state names also require an Alembic migration for database check constraints; changing only edges requires code/tests, not a database migration. Historical rows are never rewritten to match a newer graph.

## Originating decision validation

A supplied `originating_decision_id` must identify an `iterate` decision of the same hypothesis whose `from_version_id` is the current version. The hypothesis must still be in `ITERATION`, and that decision must be the one attached to the latest transition into this iteration. An older decision cannot be reused after returning to research and entering a later iteration, even if the version has not changed. Non-iteration decisions and already-consumed origins are rejected with `422` before inserting a version or moving the current pointer.

The origin remains optional: manually creating a version without a decision link is still allowed. A missing decision ID returns `404`. No schema migration or rewriting of existing historical links is performed.
