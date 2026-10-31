import json

import pytest

from src.decision_log import DecisionLog
from src.ingest import normalize
from src.route import route
from tests.test_setup import DATA

HIT = [{"doc_id": "DOC-API-001", "score": 0.7}]


def cls(intent="rate_limit", conf=0.95, p_auto=0.95, fallback=False):
    return {"fallback": fallback, "p_auto": p_auto, "intent": {"value": intent, "confidence": conf}}


def test_classification_has_class_confidence_and_alternatives(classifier):
    out = classifier.classify(normalize({"body": "We get 429 Too Many Requests from the API every afternoon"}))
    for k in ("intent", "urgency"):
        assert isinstance(out[k]["value"], str) and 0 <= out[k]["confidence"] <= 1
        assert len(out[k]["alternatives"]) == 2
    assert out["intent"]["value"] == "rate_limit" and 0 <= out["p_auto"] <= 1


def test_same_ticket_same_decision(classifier, retriever):
    t = normalize(json.loads((DATA / "validation_tickets.json").read_text())[0])
    decisions = [route(classifier.classify(t), retriever.search(t.text)) for _ in range(2)]
    assert decisions[0] == decisions[1]


def test_empty_ticket_falls_back_and_escalates(classifier):
    out = classifier.classify(normalize({"body": "   "}))
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


def test_decision_log_round_trip(tmp_path):
    log = DecisionLog(f"sqlite:///{tmp_path / 'd.db'}")
    log.write(ticket_id="T-1", stage="routing", prediction={"value": "rate_limit", "confidence": 0.9},
              action_taken="escalate", reason="test")
    [row] = log.rows(ticket_id="T-1")
    assert row["prediction"]["confidence"] == 0.9 and row["decision_id"] and row["timestamp"]
    with pytest.raises(AssertionError):
        log.write(ticket_id="T-2", not_a_field=1)
