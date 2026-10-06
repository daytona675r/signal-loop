"""Create an example hypothesis, research real HN comments, and stop for human review.

Requires the Compose API/database to be running. Does not approve its own output.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def run(base_url, query, limit):
    def request(path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = Request(
            base_url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urlopen(req, timeout=15) as response:
                return json.load(response)
        except HTTPError as error:
            raise RuntimeError(error.read().decode()) from error

    request("/health")
    hypothesis = request(
        "/hypotheses",
        {
            "title": "Removable rear storage — v0.2 research example",
            "domain": "Camper / Vanlife / Overlanding",
            "created_by": "research-demo",
            "version": {
                "target_customer": "Camper and dual-use van owners",
                "problem": "Existing storage may require permanent installation (assumption).",
                "offer": "Removable modular rear storage without drilling (assumption).",
                "price_assumption": "449.00",
                "currency": "EUR",
                "success_criteria": (
                    "Human assesses whether retrieved comments are relevant evidence."
                ),
                "change_reason": "Initial unvalidated research example",
                "created_by": "research-demo",
            },
        },
    )
    print(f"Created example hypothesis {hypothesis['id']}; beliefs are unvalidated.", flush=True)
    print(f"Searching real Hacker News comments for {query!r} (up to {limit}).", flush=True)
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "api",
            "python",
            "-m",
            "signalloop.research",
            "--version",
            hypothesis["current_version_id"],
            "--query",
            query,
            "--limit",
            str(limit),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    if completed.returncode:
        print(completed.stderr, file=sys.stderr)
        print(
            "Research failed. Inspect the reported AgentRun; no automatic retry was attempted.",
            file=sys.stderr,
        )
        return 1
    result = json.loads(completed.stdout)
    run_id = result["agent_run_id"]
    review = request(f"/research-runs/{run_id}")
    current = request(f"/hypotheses/{hypothesis['id']}")
    if current != hypothesis or review["review_status"] != "awaiting_review":
        raise RuntimeError("Research did not preserve the expected human-review boundary")
    print(
        f"SUCCESS: {len(result['source_ids'])} Sources "
        f"and {len(result['evidence_ids'])} Evidence records."
    )
    if not result["materials"]:
        print(
            "No usable results. This is an empty search, not evidence that the problem is absent."
        )
    print("State remains DRAFT. No decisions, experiments or market signals were created.")
    print(f"STOPPED FOR HUMAN REVIEW: {base_url}/research-runs/{run_id}")
    print(f"Evidence: {base_url}/hypotheses/{hypothesis['id']}/evidence")
    print("To review manually, open /docs -> POST /human-reviews and supply your own decision:")
    print(
        json.dumps(
            {
                "agent_run_id": run_id,
                "decision": "approved or rejected",
                "notes": "Your assessment after reading the evidence",
                "reviewed_by": "your-name",
            },
            indent=2,
        )
    )
    print(
        "No review was submitted by this demo. "
        "Search matches may be irrelevant; inspect each source."
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--query", default="van storage")
    parser.add_argument("--limit", type=int, choices=range(1, 21), default=3, metavar="1..20")
    args = parser.parse_args()
    sys.exit(run(args.base_url, args.query, args.limit))
