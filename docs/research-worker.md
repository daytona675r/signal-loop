# Foundation v0.2: one synchronous research loop

The parent issue #3 orders P0 tasks #4–#9; each child is verified by CI before the next begins. Development uses `foundation-v0.2`, with CI also retaining v0.1 triggers.

`ResearchWorker.run(ResearchCommand(...))` is the synchronous application entrypoint. Commands require a concrete `hypothesis_version_id`, nonblank search query and result limit (1–20). The worker loads the immutable version into a typed input and validates normalized output against that version and limit. Missing versions fail with 404 before any source call. There is no conversation memory, scheduler, queue or implicit current-version fallback.

The one selected source is public Hacker News comments via [Algolia's documented HN API](https://hn.algolia.com/api). This is a deliberately small first channel, not a claim that Hacker News represents the camper market. Search matches require human judgment; a comment excerpt is evidence of what someone wrote, not proof of demand. No model is required to extract factual excerpts.

Implementation checkpoints: #4 contracts/entrypoint; #5 durable run lifecycle; #6 concrete adapter; #7 transactional sources/evidence; #8 human-review boundary; #9 end-to-end acceptance and demo.
