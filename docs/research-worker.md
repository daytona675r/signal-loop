# Foundation v0.2: one synchronous research loop

The parent issue #3 orders P0 tasks #4–#9; each child is verified by CI before the next begins. Development uses `foundation-v0.2`, with CI also retaining v0.1 triggers.

`ResearchWorker.run(ResearchCommand(...))` is the synchronous application entrypoint. Commands require a concrete `hypothesis_version_id`, nonblank search query and result limit (1–20). The worker loads the immutable version into a typed input and validates normalized output against that version and limit. Missing versions fail with 404 before any source call. There is no conversation memory, scheduler, queue or implicit current-version fallback.

The one selected source is public Hacker News comments via [Algolia's documented HN API](https://hn.algolia.com/api). This is a deliberately small first channel, not a claim that Hacker News represents the camper market. Search matches require human judgment; a comment excerpt is evidence of what someone wrote, not proof of demand. No model is required to extract factual excerpts.

Implementation checkpoints: #4 contracts/entrypoint; #5 durable run lifecycle; #6 concrete adapter; #7 transactional sources/evidence; #8 human-review boundary; #9 end-to-end acceptance and demo.

## Durable execution (#5)

A research run records `pending` in its own committed transaction, then `running` with `started_at` before the collector is invoked. The exact command and version snapshot are retained, with an additional relational version FK on AgentRun (migration `0004`). Validation rejects output for another version or more than the requested number of items. Only validated output can commit alongside `succeeded`, finish time and latency. No model/provider is invented when no model is called.

Caught source, validation and persistence errors roll back work, then commit a `failed` run with stage/type/error context in a new transaction. The caller receives a `ResearchFailed` domain error carrying the run ID. There is no retry. A process kill or database outage can prevent a final status write; the last committed pending/running record remains, and automated recovery is deliberately not introduced. Existing manual AgentRun endpoints remain compatible.

## One source and synchronous execution (#6)

The concrete adapter makes one request to `https://hn.algolia.com/api/v1/search`, with `tags=comment`, the explicit query, page zero and the requested limit. It uses bounded timeouts and a 2 MB decoded-response limit. Redirects, pagination, retry, implicit deduplication and secondary URL fetching are absent. Normalization preserves the canonical comment URL, ID, author, title, original HTML, search query and capture/publication times. HTML becomes plain text without model inference; malformed responses fail the run. Deleted/empty comments are counted as skipped. An empty material list is a successful empty search, not evidence of absence or validation.

Run outside the HTTP server (replace the version UUID):

```bash
docker compose exec -T api python -m signalloop.research --version VERSION_UUID --query 'van storage' --limit 5
```

The CLI prints the validated result and run ID as JSON; errors exit nonzero and include the durable run ID when available. Network tests use `httpx.MockTransport` against the real adapter, not another channel implementation. CI never depends on the external API being online.

## Version-bound persistence (#7)

Every normalized comment produces one Source (canonical URL, external ID, capture time, content hash and capture metadata) and one Evidence record containing the factual excerpt. Both carry `created_by_type=agent`, `created_by=research-worker-v0.2` and the originating run FK. Evidence stance is `unknown`, with explicitly unassessed relevance; text search is not a relevance assessment or an LLM conclusion.

The requested version is retained even if another transaction creates v2 during collection. All source/evidence inserts, their IDs in the output snapshot, and run success commit atomically. A failure after a source or evidence insert rolls them back while the separately recorded run becomes failed. An empty search creates neither sources nor evidence. Repeating a command creates a new run and fresh records; there is no hidden retry or deduplication policy. No Signals, Decisions, Experiments or state transitions are created.

## Mandatory human-review boundary (#8)

A successful output includes `review_target: {"agent_run_id": "..."}`. The AgentRun itself is the persisted review target; the worker does **not** insert a HumanReview with an invented human decision. This preserves the existing exactly-one-target invariant and prevents auto-approval.

- `GET /research-runs?awaiting_review=true` discovers successful runs with no recorded review.
- Add `hypothesis_version_id=UUID` to filter by the researched version; normal list pagination applies.
- `GET /research-runs/{id}` exposes `review_status`, the target, review IDs and latest recorded decision.
- A human explicitly calls `POST /human-reviews` with `agent_run_id`, `decision`, `notes` and `reviewed_by`.

Pending/running/failed research runs are `not_ready` and reject review with 409. Successful runs start `awaiting_review`; any explicit review changes discovery status to `reviewed` and exposes its decision (`approved`, `rejected`, `modified` or `escalated`). `reviewed` does not mean approved. Modification/escalation notes are available for further manual follow-up. The successful output snapshot retains the original review target; the read endpoint reports current review state.

Neither research completion nor any review outcome creates Decisions, Signals, experiments, versions or state transitions. Approval does not resume execution. Reviewer identity is still a caller assertion because authentication remains out of scope. Existing non-research HumanReview behavior remains compatible.


## Acceptance and operation (#9)

`tests/test_research_e2e.py` demonstrates API-created hypothesis/version → synchronous worker → durable AgentRun → the real HN adapter with mocked HTTP → Source → version-bound Evidence → an explicit HumanReview. It verifies unchanged hypothesis state, decisions and experiments, then creates v2 separately and proves v1 evidence stays on v1. Failure tests cover adapter/schema errors, an actual PostgreSQL FK violation after partial persistence, and a missing version with zero side effects. Existing v0.1 tests remain unchanged. The same GitHub Actions workflow automatically runs the entire suite.

For a live demonstration, start Compose and run `python scripts/research_demo.py`. It creates example assumptions, retrieves actual source comments, and prints the completed run and evidence links without submitting any approval. Human approval/rejection is a separate Swagger/API action. The fixture-based CI tests do not depend on the public source API's availability or search ranking.

## Developer verification

The final local and Python 3.12 container runs passed 77 tests. Alembic reports `0004 (head)` with no drift. All original v0.1 test files are unchanged. One existing Starlette/httpx TestClient deprecation warning remains; it does not affect the passing checks.

A live demonstration retrieved three real comments for `van storage`, wrote three Sources and three Evidence records, and retained `DRAFT` with no human review submitted:

- [Inspect the live run](http://localhost:8000/research-runs/a128ed35-571f-4a63-add1-6e4398ebe086)
- [Inspect its evidence](http://localhost:8000/hypotheses/c704b831-7d5a-4af6-9c6d-89d26509a4ae/evidence)

These links refer to the current local database. The search confirms working retrieval/provenance, not relevance or market validation. Limitations remain explicit: one source, no LLM assessment, no automatic retry/deduplication or crash recovery, unauthenticated human identifiers, and no autonomous execution after review.
