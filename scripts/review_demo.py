"""Run a narrated live API review; all newly created business data is simulated."""

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def run(base_url, output=None, pause=False):
    base_url = base_url.rstrip("/")
    checks = []
    records = {}
    completed = False

    def stage(title):
        print(f"\n{title}", flush=True)
        if pause:
            input("Press Enter to demonstrate this section...")

    def check(description, condition, details=None):
        entry = {"check": description, "passed": bool(condition), "details": details}
        checks.append(entry)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}", flush=True)
        if not condition:
            raise RuntimeError(f"Review check failed: {description}: {details}")

    def request(path, payload=None, method=None, expected=200):
        data = json.dumps(payload).encode() if payload is not None else None
        req = Request(
            base_url + path, data=data, method=method, headers={"Content-Type": "application/json"}
        )
        try:
            with urlopen(req, timeout=15) as response:
                status, body = response.status, json.load(response)
        except HTTPError as error:
            status, body = error.code, json.load(error)
        if status != expected:
            raise RuntimeError(f"{req.method} {path}: expected {expected}, got {status}: {body}")
        return body

    def post(path, data):
        return request(path, data, expected=201)

    started = datetime.now(UTC).isoformat()
    try:
        stage("1. Running API and discoverable contracts")
        check("Database-backed health endpoint", request("/health") == {"status": "ok"})
        spec = request("/openapi.json")
        check(
            "OpenAPI exposes versions, decisions, reviews and runs",
            all(
                path in spec["paths"]
                for path in (
                    "/hypotheses/{hypothesis_id}/versions",
                    "/agent-runs",
                    "/human-reviews",
                    "/hypotheses/{hypothesis_id}/decisions",
                )
            ),
        )

        stage("2. Complete manual lifecycle: assumptions -> observations -> decision -> v2")
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("manual_loop.py")),
                "--base-url",
                base_url,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        summary = json.loads(result.stdout)
        records["hypothesis_id"] = summary["hypothesis_id"]
        root = f"/hypotheses/{summary['hypothesis_id']}"
        hypothesis = request(root)
        v1, v2 = request(root + "/versions/1"), request(root + "/versions/2")
        history = request(root + "/history")
        evidence = request(root + "/evidence")
        experiments = request(root + "/experiments")
        signals = request(f"/experiments/{experiments[0]['id']}/signals")
        decisions = request(root + "/decisions")
        records.update(
            version_1_id=v1["id"],
            version_2_id=v2["id"],
            experiment_id=experiments[0]["id"],
            decision_id=decisions[0]["id"],
        )
        check(
            "v1 remains EUR 449; v2 is EUR 349",
            v1["price_assumption"] == "449.00" and v2["price_assumption"] == "349.00",
        )
        check(
            "Current version is v2; final state is RESEARCH",
            hypothesis["current_version_id"] == v2["id"] and hypothesis["status"] == "RESEARCH",
        )
        expected_states = [
            "DRAFT",
            "FEASIBILITY",
            "RESEARCH",
            "READY_FOR_EXPERIMENT",
            "EXPERIMENT",
            "EVALUATION",
            "ITERATION",
            "RESEARCH",
        ]
        check(
            "Eight ordered history entries preserve the lifecycle",
            [row["to_state"] for row in history] == expected_states
            and [row["sequence_no"] for row in history] == list(range(1, 9)),
            expected_states,
        )
        check(
            "Original experiment still tests v1",
            experiments[0]["hypothesis_version_id"] == v1["id"],
        )
        source = request(f"/sources/{evidence[0]['source_id']}")
        check(
            "Evidence retains its source and tested version",
            evidence[0]["hypothesis_version_id"] == v1["id"]
            and source["metadata"]["simulated"] is True,
        )
        check(
            "Three simulated observations remain distinct from assumptions",
            {row["signal_type"] for row in signals}
            == {"page_view", "email_submit", "price_objection"}
            and all(row["raw_payload"]["simulated"] for row in signals),
        )
        check(
            "Decision cites evidence/signals and explains v2",
            decisions[0]["supporting_evidence_ids"] == [evidence[0]["id"]]
            and set(decisions[0]["supporting_signal_ids"]) == {row["id"] for row in signals}
            and decisions[0]["resulting_version_ids"] == [v2["id"]],
        )
        print(f"  Inspect: {base_url}{root}\n  History: {base_url}{root}/history", flush=True)

        stage("3. Invalid actions fail without changing durable state")
        response = request(
            root + "/transition",
            {
                "target_state": "VALIDATED",
                "reason": "Review: attempt to skip evaluation",
            },
            expected=409,
        )
        check(
            "Skipping from RESEARCH to VALIDATED returns 409",
            "Invalid transition" in response["detail"],
            response,
        )
        request(
            root + "/decisions",
            {"decision": "validate", "rationale": "Simulated invalid action"},
            expected=409,
        )
        check(
            "Rejected decision leaves decisions and history unchanged",
            request(root + "/decisions") == decisions and request(root + "/history") == history,
        )
        request(root + "/versions/1", {"price_assumption": "0.00"}, method="PATCH", expected=405)
        check(
            "No version overwrite endpoint; v1 stays unchanged", request(root + "/versions/1") == v1
        )
        request(
            root + "/evidence",
            {"quote_or_summary": "Missing source review example", "source_id": str(uuid4())},
            expected=404,
        )
        check("Unknown source cannot create evidence", request(root + "/evidence") == evidence)
        request(
            f"/experiments/{experiments[0]['id']}/signals",
            {
                "signal_type": "email_submit",
                "observation": "Simulated invalid timestamp",
                "occurred_at": "2026-01-01T10:00:00",
            },
            expected=422,
        )
        check(
            "Timezone-less event rejected; no additional signal",
            request(f"/experiments/{experiments[0]['id']}/signals") == signals,
        )
        other = post(
            "/hypotheses",
            {
                "title": "Cross-hypothesis integrity fixture (simulated review)",
                "domain": "review",
                "version": {
                    key: v1[key]
                    for key in (
                        "target_customer",
                        "problem",
                        "offer",
                        "price_assumption",
                        "currency",
                        "success_criteria",
                        "change_reason",
                    )
                },
            },
        )
        records["integrity_fixture_hypothesis_id"] = other["id"]
        request(
            root + "/evidence",
            {
                "quote_or_summary": "Cross-hypothesis review test",
                "hypothesis_version_id": other["current_version_id"],
            },
            expected=422,
        )
        check(
            "Another hypothesis's version cannot receive this hypothesis's evidence",
            request(root + "/evidence") == evidence,
        )

        stage("4. Future worker trace and human review, with no agent execution")
        run_record = post(
            "/agent-runs",
            {
                "agent_role": "review-fixture",
                "run_type": "manual-simulation",
                "status": "succeeded",
                "provider": "simulated-provider",
                "model": "no-model-called",
                "prompt_version": "review-v1",
                "input_snapshot": {"hypothesis_version_id": v2["id"]},
                "output_snapshot": {
                    "interpretation": "Price needs further validation.",
                    "simulated": True,
                },
                "cost": "0",
                "latency_ms": 0,
            },
        )
        review = post(
            "/human-reviews",
            {
                "agent_run_id": run_record["id"],
                "decision": "approved",
                "reviewed_by": "review-demo",
                "notes": (
                    "Simulated review of a fixture; no external action authorized or executed."
                ),
            },
        )
        records.update(agent_run_id=run_record["id"], human_review_id=review["id"])
        stored_run = request(f"/agent-runs/{run_record['id']}")
        # PostgreSQL returns NUMERIC at its declared scale; compare numeric values.
        check(
            "Provider-neutral run snapshot is retrievable",
            {**stored_run, "cost": Decimal(stored_run["cost"])}
            == {**run_record, "cost": Decimal(run_record["cost"])},
            {"submitted_cost": run_record["cost"], "stored_cost": stored_run["cost"]},
        )
        check(
            "Human review retains reviewer and concrete target",
            request(f"/human-reviews/{review['id']}") == review,
        )
        check(
            "Interpretation/review did not create market signals or change state",
            request(f"/experiments/{experiments[0]['id']}/signals") == signals
            and request(root) == hypothesis,
        )
        completed = True
    finally:
        report = {
            "completed": completed,
            "started_at": started,
            "finished_at": datetime.now(UTC).isoformat(),
            "base_url": base_url,
            "simulated_data": True,
            "records": records,
            "checks": checks,
            "passed_checks": sum(row["passed"] for row in checks),
        }
        if output:
            Path(output).write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nReview complete: {len(checks)}/{len(checks)} checks passed.", flush=True)
    print("Created two simulated hypotheses plus linked demo records; existing data was retained.")
    if output:
        print(f"Evidence report: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output", help="Write the observed checks and record IDs as JSON")
    parser.add_argument("--pause", action="store_true", help="Pause before each review section")
    args = parser.parse_args()
    run(args.base_url, args.output, args.pause)
