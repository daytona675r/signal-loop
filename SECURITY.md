# Security and public-readiness notes

SignalLoop is a local portfolio application, not a hosted service. The
checked-in `.env.example` uses disposable local PostgreSQL credentials; copy it
to `.env` for development and never replace those values with real secrets in
Git.

The example scripts create simulated hypotheses and observations. The research
worker reads public Hacker News comments through Algolia, stores source URLs
and evidence provenance, and stops for explicit human review. It does not
contain API keys, private notes, authentication tokens or customer data.

Before hosting the API, add authentication, rate limits, secret management,
network restrictions and a managed PostgreSQL backup policy. The current
Compose setup is for local review only.
