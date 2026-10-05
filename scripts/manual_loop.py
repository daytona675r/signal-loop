"""Execute the Foundation acceptance scenario against a running API (stdlib only).

Creates clearly marked simulated observations; does not perform real market research.
"""

import argparse
import json
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def run(base_url):
    def request(path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = Request(
            base_url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urlopen(req, timeout=15) as response:
                return json.load(response)
        except HTTPError as error:
            raise RuntimeError(f"{req.method} {path}: {error.read().decode()}") from error

    version = {
        "target_customer": (
            "Fiat Ducato / Citroën Jumper / Peugeot Boxer camper and dual-use owners"
        ),
        "problem": "Existing organised storage solutions often require permanent installation.",
        "offer": "Removable modular rear storage system without permanent vehicle modifications.",
        "price_assumption": "449.00",
        "currency": "EUR",
        "success_criteria": (
            "Validate demand and willingness to pay; these are unvalidated assumptions."
        ),
        "change_reason": "Initial assumptions",
        "created_by": "mario",
    }
    hypothesis = request(
        "/hypotheses",
        {
            "title": "Removable Modular Rear Storage System (simulated example)",
            "domain": "Camper / Vanlife / Overlanding",
            "version": version,
            "created_by": "mario",
        },
    )
    root = f"/hypotheses/{hypothesis['id']}"

    def move(state):
        request(
            root + "/transition",
            {
                "target_state": state,
                "reason": "Manual acceptance example",
                "created_by": "mario",
            },
        )

    original = request(root + "/versions/1")
    move("FEASIBILITY")
    move("RESEARCH")
    source = request(
        "/sources",
        {
            "source_type": "manual_observation",
            "title": "Simulated example, not real customer research",
            "metadata": {"simulated": True},
            "created_by": "mario",
        },
    )
    evidence = request(
        root + "/evidence",
        {
            "source_id": source["id"],
            "quote_or_summary": "I don't want to drill holes into my van.",
            "stance": "supports",
            "structured_facts": {"simulated": True},
            "created_by": "mario",
        },
    )
    move("READY_FOR_EXPERIMENT")
    experiment = request(
        root + "/experiments",
        {
            "name": "Landing Page Demand Test",
            "objective": "Measure CTA conversion rate",
            "channel": "simulated landing page",
            "price_test": "449.00",
            "success_criteria": "CTA conversion rate >= 5% (illustrative threshold)",
        },
    )
    move("EXPERIMENT")
    signals = [
        request(
            f"/experiments/{experiment['id']}/signals",
            {
                "signal_type": kind,
                "value": 1,
                "occurred_at": datetime.now(UTC).isoformat(),
                "observation": f"Simulated {kind} for API acceptance demonstration",
                "raw_payload": {"simulated": True},
            },
        )
        for kind in ("page_view", "email_submit", "price_objection")
    ]
    move("EVALUATION")
    decision = request(
        root + "/decisions",
        {
            "decision": "iterate",
            "rationale": (
                "Problem evidence looks promising, "
                "but price sensitivity still needs validation. Simulated example only."
            ),
            "supporting_evidence_ids": [evidence["id"]],
            "supporting_signal_ids": [item["id"] for item in signals],
        },
    )
    new_version = request(
        root + "/versions",
        {
            **version,
            "price_assumption": "349.00",
            "change_reason": "Test lower price assumption",
            "originating_decision_id": decision["id"],
        },
    )
    move("RESEARCH")
    assert request(root + "/versions/1") == original
    assert new_version["version_no"] == 2
    assert request(root)["status"] == "RESEARCH"
    history = request(root + "/history")
    assert len(history) == 8
    assert request(root + "/decisions")[0]["resulting_version_ids"] == [new_version["id"]]
    print(
        json.dumps(
            {
                "hypothesis_id": hypothesis["id"],
                "v1_price": original["price_assumption"],
                "v2_price": new_version["price_assumption"],
                "status": "RESEARCH",
                "history_records": len(history),
                "simulated": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    run(parser.parse_args().base_url)
