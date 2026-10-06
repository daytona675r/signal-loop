"""Origins must explain this iteration, not an unrelated historical decision."""

import pytest


def post(client, path, payload):
    response = client.post(path, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def transition(client, root, state):
    return post(client, root + "/transition", {"target_state": state, "reason": "Origin test"})


def research(client, root):
    transition(client, root, "FEASIBILITY")
    transition(client, root, "RESEARCH")


def decide(client, root, decision):
    return post(client, root + "/decisions", {"decision": decision, "rationale": "Origin test"})


def assert_rejected_without_changes(client, root, version_fields, decision_id):
    before = {
        path: client.get(root + path).json() for path in ("", "/versions", "/history", "/decisions")
    }
    response = client.post(
        root + "/versions",
        json={
            **version_fields,
            "originating_decision_id": decision_id,
        },
    )
    assert response.status_code == 422, response.text
    for path, value in before.items():
        assert client.get(root + path).json() == value


def test_current_iteration_decision_creates_linked_version(client, hypothesis, hypothesis_payload):
    root = f"/hypotheses/{hypothesis['id']}"
    research(client, root)
    decision = decide(client, root, "iterate")
    original = client.get(root + "/versions/1").json()
    version = post(
        client,
        root + "/versions",
        {
            **hypothesis_payload["version"],
            "originating_decision_id": decision["id"],
        },
    )
    assert version["version_no"] == 2
    assert client.get(root).json()["current_version_id"] == version["id"]
    assert client.get(root + "/versions/1").json() == original
    assert client.get(root + "/decisions").json()[0]["resulting_version_ids"] == [version["id"]]


@pytest.mark.parametrize("kind", ["continue", "pause", "reject", "validate"])
def test_non_iteration_decision_cannot_originate_version(
    client, hypothesis, hypothesis_payload, kind
):
    root = f"/hypotheses/{hypothesis['id']}"
    research(client, root)
    if kind == "validate":
        for state in ("READY_FOR_EXPERIMENT", "EXPERIMENT", "EVALUATION"):
            transition(client, root, state)
    decision = decide(client, root, kind)
    if kind == "continue":
        # Even in ITERATION, an earlier continue decision cannot explain the next version.
        decide(client, root, "iterate")
    assert_rejected_without_changes(client, root, hypothesis_payload["version"], decision["id"])


def test_other_hypothesis_iteration_decision_rejected(client, hypothesis, hypothesis_payload):
    root = f"/hypotheses/{hypothesis['id']}"
    research(client, root)
    decide(client, root, "iterate")
    other = post(client, "/hypotheses", hypothesis_payload)
    other_root = f"/hypotheses/{other['id']}"
    research(client, other_root)
    decision = decide(client, other_root, "iterate")
    assert_rejected_without_changes(client, root, hypothesis_payload["version"], decision["id"])


def test_previous_version_iteration_decision_cannot_be_reused(
    client, hypothesis, hypothesis_payload
):
    root = f"/hypotheses/{hypothesis['id']}"
    research(client, root)
    decision = decide(client, root, "iterate")
    post(
        client,
        root + "/versions",
        {
            **hypothesis_payload["version"],
            "originating_decision_id": decision["id"],
        },
    )
    assert_rejected_without_changes(client, root, hypothesis_payload["version"], decision["id"])


def test_origin_rejected_after_leaving_iteration(client, hypothesis, hypothesis_payload):
    root = f"/hypotheses/{hypothesis['id']}"
    research(client, root)
    decision = decide(client, root, "iterate")
    transition(client, root, "RESEARCH")
    assert_rejected_without_changes(client, root, hypothesis_payload["version"], decision["id"])


@pytest.mark.parametrize("reentry", ["decision", "manual"])
def test_earlier_cycle_of_same_version_is_not_current_origin(
    client,
    hypothesis,
    hypothesis_payload,
    reentry,
):
    root = f"/hypotheses/{hypothesis['id']}"
    research(client, root)
    old = decide(client, root, "iterate")
    transition(client, root, "RESEARCH")
    if reentry == "decision":
        latest = decide(client, root, "iterate")
    else:
        transition(client, root, "ITERATION")
    assert_rejected_without_changes(client, root, hypothesis_payload["version"], old["id"])
    if reentry == "decision":
        version = post(
            client,
            root + "/versions",
            {
                **hypothesis_payload["version"],
                "originating_decision_id": latest["id"],
            },
        )
        assert version["version_no"] == 2


def test_unlinked_manual_version_remains_allowed(client, hypothesis, hypothesis_payload):
    root = f"/hypotheses/{hypothesis['id']}"
    version = post(client, root + "/versions", hypothesis_payload["version"])
    assert version["version_no"] == 2
    assert version["originating_decision_id"] is None
