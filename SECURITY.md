# Security and public-readiness notes

SignalLoop is a local portfolio application, not a hosted service. Public source
code and a public running API are separate decisions: this repository may be
reviewed as source while its API and PostgreSQL database remain local-only.
The checked-in `.env.example` uses disposable local PostgreSQL credentials;
copy it to `.env` for development and never replace those values with real
secrets in Git.

The example scripts create simulated hypotheses and observations. The research
worker reads public Hacker News comments through Algolia, stores source URLs
and evidence provenance, and stops for explicit human review. It does not run
an LLM, make autonomous approvals or establish market validation. Reviewer and
producer identities in the API are asserted metadata, not authenticated
identities. Writable endpoints are therefore unsafe to expose to an anonymous
internet client.

The current Compose setup binds the API and database to loopback for local
review only. `render.yaml` is a non-production reference blueprint and is
disabled for public use; do not deploy it as-is. Any future hosting decision
requires authentication, rate limits, secret management, network restrictions,
database isolation/backups, migration controls, sanitized errors and a
read-only or resettable demo policy. The research worker may persist raw
exception detail in `AgentRun.error`, which must be reviewed before hosting.

No public deployment or repository-visibility change has been made.
