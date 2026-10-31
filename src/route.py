"""Route: auto-respond or escalate, deterministically, with a reason a support manager can read (A5).

Rules are checked in order; the first that fires decides. Thresholds come from
evaluation/routing_threshold.py on dev tickets (out-of-fold): at 0.85, 18% of tickets auto-respond and
12 of those 90 should have escalated; at 0.80 it is 29% and 24 of 145. 0.85 favours fewer wrong answers,
which the Head of Support named as the first failure condition. No threshold auto-responds a
must_not_auto_respond ticket.
"""
import os

# FR-04. The first four are labelled must_not_auto_respond on every ticket (evidence E13); data_residency is
# added because the Tier Two engineer says data-location mistakes become compliance problems (PRD decision 1).
MUST_ESCALATE = {"security_incident", "compliance_request", "feature_request", "unclear_request", "data_residency"}
ROUTE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.85"))
INTENT_MIN = float(os.getenv("INTENT_MIN_CONFIDENCE", "0.50"))


def route(cls: dict, hits: list[dict], threshold: float = ROUTE_THRESHOLD, intent_min: float = INTENT_MIN) -> dict:
    intent, conf, p = cls["intent"]["value"], cls["intent"]["confidence"], cls["p_auto"]
    # (fired, reason, PRD requirements behind the rule) so the decision log can say which requirement decided.
    checks = [
        (cls["fallback"], "The ticket has no readable text, so it needs a person.", ["FR-01", "FR-05"]),
        (intent in MUST_ESCALATE, f"'{intent}' tickets always go to a person.", ["FR-04"]),
        (conf < intent_min, f"Unsure what the customer is asking (best guess '{intent}', {conf:.0%} confident).",
         ["FR-02", "FR-05"]),
        (not hits, "No documentation passage is relevant enough to answer from.", ["FR-03", "FR-05"]),
        (p < threshold, f"Only {p:.0%} likely to be answerable without a person; the bar is {threshold:.0%}.",
         ["FR-05"]),
    ]
    for fired, reason, reqs in checks:
        if fired:
            return {"action": "escalate", "reason": reason, "threshold_applied": threshold, "requirement_ids": reqs}
    return {"action": "auto_respond", "threshold_applied": threshold, "requirement_ids": ["FR-05"],
            "reason": f"Recognised as '{intent}' ({conf:.0%} confident), {p:.0%} likely answerable from "
                      f"{hits[0]['doc_id']}."}
