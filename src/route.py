"""Route: auto-respond or escalate, deterministically, with a reason a support manager can read (A5).

Rules are checked in order; the first that fires decides. Thresholds come from
evaluation/routing_threshold.py on dev tickets (out-of-fold): at 0.85, 20% of tickets auto-respond and
13 of those 100 should have escalated; at 0.80 it is 32% and 27 of 160. 0.85 favours fewer wrong answers,
which the Head of Support named as the first failure condition. No threshold auto-responds a
must_not_auto_respond ticket.
"""
import os

# Every dev/validation ticket with these intents is labelled must_not_auto_respond (evidence E13).
MUST_ESCALATE = {"security_incident", "compliance_request", "feature_request", "unclear_request"}
ROUTE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.85"))
INTENT_MIN = float(os.getenv("INTENT_MIN_CONFIDENCE", "0.50"))


def route(cls: dict, hits: list[dict], threshold: float = ROUTE_THRESHOLD, intent_min: float = INTENT_MIN) -> dict:
    intent, conf, p = cls["intent"]["value"], cls["intent"]["confidence"], cls["p_auto"]
    checks = [
        (cls["fallback"], "The ticket has no readable text, so it needs a person."),
        (intent in MUST_ESCALATE, f"'{intent}' tickets always go to a person."),
        (conf < intent_min, f"Unsure what the customer is asking (best guess '{intent}', {conf:.0%} confident)."),
        (not hits, "No documentation passage is relevant enough to answer from."),
        (p < threshold, f"Only {p:.0%} likely to be answerable without a person; the bar is {threshold:.0%}."),
    ]
    for fired, reason in checks:
        if fired:
            return {"action": "escalate", "reason": reason, "threshold_applied": threshold}
    return {"action": "auto_respond", "threshold_applied": threshold,
            "reason": f"Recognised as '{intent}' ({conf:.0%} confident), {p:.0%} likely answerable from "
                      f"{hits[0]['doc_id']}."}
