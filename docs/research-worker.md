# Foundation v0.2: one synchronous research loop

The parent issue #3 orders P0 tasks #4–#9; each child is verified by CI before the next begins. Development uses `foundation-v0.2`, with CI also retaining v0.1 triggers.

`ResearchWorker.run(ResearchCommand(...))` is the synchronous application entrypoint. Commands require a concrete `hypothesis_version_id`, nonblank search query and result limit (1–20). The worker loads the immutable version into a typed input and validates normalized output against that version and limit. Missing versions fail with 404 before any source call. There is no conversation memory, scheduler, queue or implicit current-version fallback.

The one selected source is public Hacker News comments via [Algolia's documented HN API](https://hn.algolia.com/api). This is a deliberately small first channel, not a claim that Hacker News represents the camper market. Search matches require human judgment; a comment excerpt is evidence of what someone wrote, not proof of demand. No model is required to extract factual excerpts.

Implementation checkpoints: #4 contracts/entrypoint; #5 durable run lifecycle; #6 concrete adapter; #7 transactional sources/evidence; #8 human-review boundary; #9 end-to-end acceptance and demo.

## Durable execution (#5)

A research run records `pending` in its own committed transaction, then `running` with `started_at` before the collector is invoked. The exact command and version snapshot are retained, with an additional relational version FK on AgentRun (migration `0004`). Validation rejects output for another version or more than the requested number of items. Only validated output can commit alongside `succeeded`, finish time and latency. No model/provider is invented when no model is called.

Caught source, validation and persistence errors roll back work, then commit a `failed` run with stage/type/error context in a new transaction. The caller receives a `ResearchFailed` domain error carrying the run ID. There is no retry. A process kill or database outage can prevent a final status write; the last committed pending/running record remains, and automated recovery is deliberately not introduced. Existing manual AgentRun endpoints remain compatible.
