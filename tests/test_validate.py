import json
import re

import pytest

from src.ingest import normalize
from src.llm import LLMUnavailable
from src.validate import find_commitments, validate
from tests.test_setup import DATA

TICKET = normalize({"ticket_id": "T-9", "customer_id": "CUST-1042", "customer_name": "Priya Sharma",
                    "body": "We keep hitting 429 errors"})
PASSAGES = [{"chunk_id": "DOC-API-001#resolution", "text": "Limits apply per organisation. Retry with backoff."}]


def judge(*verdicts, raw=None):
    def llm(system, user):
        llm.calls += 1
        if isinstance(raw, Exception):
            raise raw
        return {"content": raw if isinstance(raw, str) else json.dumps(
            {"results": [{"i": i, "verdict": v, "reason": ""} for i, v in enumerate(verdicts)]}), "model": "fake"}
    llm.calls = 0
    return llm


def draft(*texts):
    return [{"text": t, "cite": ["DOC-API-001#resolution"]} for t in texts]


def test_clean_grounded_draft_passes():
    out = validate(draft("Limits apply per organisation.", "Thanks for asking."), TICKET, PASSAGES,
                   llm=judge("supported", "no_claim"))
    assert out["passed"] and out["checks"] == {"pii": "pass", "commitments": "pass", "grounding": "pass"}


@pytest.mark.parametrize("text, kind", [
    ("Hi Priya Sharma, retry with backoff.", "customer name"),
    ("Your account CUST-1042 is limited.", "customer ID"),
    ("Email ops@example.com for help.", "email address"),
    ("Use key sk_live12345678abc.", "key or token"),
])
def test_private_data_blocks_without_calling_the_model(text, kind):
    llm = judge("supported")
    out = validate(draft(text), TICKET, PASSAGES, llm=llm)
    assert not out["passed"] and kind in out["found"]["private"] and llm.calls == 0


@pytest.mark.parametrize("text", [
    "A refund has been issued to your card.", "We will issue a full refund.", "The issue has been fixed on our side.",
    "The fix will be released by Friday.", "Your data is stored in the EU region.",
])
def test_forbidden_commitments_block(text):
    out = validate(draft(text), TICKET, PASSAGES, llm=judge("supported"))
    assert not out["passed"] and out["checks"]["commitments"] == "fail"


def test_unsupported_sentence_blocks():
    out = validate(draft("Limits apply per organisation.", "Limits reset every 5 minutes."), TICKET, PASSAGES,
                   llm=judge("supported", "unsupported"))
    assert not out["passed"] and "not supported" in out["blocked_reason"]


@pytest.mark.parametrize("llm", [judge(raw=LLMUnavailable("down")), judge(raw="not json"), judge("supported")])
def test_grounding_fails_closed(llm):
    # unavailable, unparseable, or the wrong number of verdicts (one verdict for two sentences)
    out = validate(draft("Limits apply per organisation.", "Retry with backoff."), TICKET, PASSAGES, llm=llm)
    assert not out["passed"] and out["checks"]["grounding"] == "fail"


def test_no_false_positives_on_reference_answers_and_docs():
    refs = [g["reference_response"] for g in json.loads((DATA / "ground_truth_responses.json").read_text())]
    docs = [p for d in json.loads((DATA / "documentation.json").read_text())
            for p in re.split(r"\n(?=## )", d["content"])[1:]]
    # One deliberate hit: a Symptoms line stating "the credit was applied", a claim about the customer's own bill.
    assert sum(bool(find_commitments(t)) for t in refs + docs) == 1
