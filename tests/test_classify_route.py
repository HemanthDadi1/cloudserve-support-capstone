import json

import pytest

from src.decision_log import DecisionLog
from src.ingest import normalize
from src.route import escalation_packet, route
from tests.test_setup import DATA

HIT = [{"doc_id": "DOC-API-001", "chunk_id": "DOC-API-001#symptoms", "score": 0.7}]


def cls(intent="rate_limit", conf=0.95, p_auto=0.95, fallback=False):
    return {"fallback": fallback, "p_auto": p_auto, "intent": {"value": intent, "confidence": conf}}


def test_classification_has_class_confidence_and_alternatives(classifier, retriever):
    t = normalize({"body": "We get 429 Too Many Requests from the API every afternoon"})
    out = classifier.classify(t, retriever.search(t.text))
    for k in ("intent", "urgency"):
        assert isinstance(out[k]["value"], str) and 0 <= out[k]["confidence"] <= 1
        assert len(out[k]["alternatives"]) == 2
    assert out["intent"]["value"] == "rate_limit" and 0 <= out["p_auto"] <= 1


def test_same_ticket_same_decision(classifier, retriever):
    t = normalize(json.loads((DATA / "validation_tickets.json").read_text())[0])
    decisions = [route(classifier.classify(t, retriever.search(t.text)), retriever.search(t.text)) for _ in range(2)]
    assert decisions[0] == decisions[1]


def test_empty_ticket_falls_back_and_escalates(classifier):
    out = classifier.classify(normalize({"body": "   "}), [])
    assert out["fallback"] and out["intent"]["value"] == "unclear_request"
    assert route(out, HIT)["action"] == "escalate"


@pytest.mark.parametrize("kwargs, hits, expected", [
    ({}, HIT, "auto_respond"),
    ({"intent": "security_incident"}, HIT, "escalate"),
    ({"intent": "data_residency"}, HIT, "escalate"),
    ({"conf": 0.3}, HIT, "escalate"),
    ({}, [], "escalate"),
    ({"p_auto": 0.5}, HIT, "escalate"),
])
def test_routing_rules(kwargs, hits, expected):
    decision = route(cls(**kwargs), hits, threshold=0.85)
    assert decision["action"] == expected and decision["reason"]
    assert decision["requirement_ids"] and all(r.startswith("FR-") for r in decision["requirement_ids"])


def test_escalation_packet_has_all_four_fields():
    p = escalation_packet("Data export keeps failing", cls(), HIT, "Only 60% likely answerable.")
    assert p["summary"] and p["likely_topic"]["value"] == "rate_limit" and p["articles"] and p["uncertainty"]
    assert escalation_packet("", cls(), [], "x")["summary"] == "(empty ticket)"


def test_decision_log_round_trip(tmp_path):
    log = DecisionLog(f"sqlite:///{tmp_path / 'd.db'}")
    log.write(ticket_id="T-1", stage="routing", prediction={"value": "rate_limit", "confidence": 0.9},
              action_taken="escalate", reason="test")
    [row] = log.rows(ticket_id="T-1")
    assert row["prediction"]["confidence"] == 0.9 and row["decision_id"] and row["timestamp"]
    with pytest.raises(AssertionError):
        log.write(ticket_id="T-2", not_a_field=1)


def test_kill_switch_escalates_everything(monkeypatch, tmp_path):
    switch = tmp_path / "AUTOMATION_OFF"
    monkeypatch.setattr("src.route.KILL_SWITCH", switch)
    assert route(cls(), HIT)["action"] == "auto_respond"
    switch.touch()  # takes effect on the next ticket, no restart
    d = route(cls(), HIT)
    assert d["action"] == "escalate" and "kill switch" in d["reason"] and d["requirement_ids"] == ["GOV-KILL-SWITCH"]


@pytest.mark.parametrize("bad", [None, float("nan"), "0.9", True])
def test_missing_or_invalid_confidence_escalates(bad):
    d = route(cls(p_auto=bad), HIT)
    assert d["action"] == "escalate" and "GOV-CONFIDENCE-FLOOR" in d["requirement_ids"]
    assert route({"fallback": False, "p_auto": 0.99}, HIT)["action"] == "escalate"  # no intent block at all


def test_numpy_scores_pass_the_confidence_floor():
    import numpy as np
    d = route({"fallback": False, "p_auto": np.float32(0.95),
               "intent": {"value": "rate_limit", "confidence": np.float64(0.95)}}, HIT, threshold=0.85)
    assert d["action"] == "auto_respond"
