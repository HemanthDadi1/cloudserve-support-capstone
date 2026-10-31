"""Route: auto-respond or escalate, deterministically, with a reason a support manager can read (A5).

Rules are checked in order; the first that fires decides. Thresholds come from
evaluation/routing_threshold.py on dev tickets (out-of-fold): at 0.85, 24% of tickets auto-respond and
17 of those 119 should have escalated; at 0.80 it is 32% and 24 of 160. 0.85 favours fewer wrong answers,
which the Head of Support named as the first failure condition. No threshold auto-responds a
must_not_auto_respond ticket.

Two governance checks come first (Governance Framework sections 4 and 5):
- Kill switch: while the file at KILL_SWITCH_PATH exists, every ticket escalates. It is read per ticket,
  so creating the file takes effect on the next ticket with no restart or deployment.
- Confidence floor: a missing or non-numeric score escalates; a missing score is not a high one.
"""
import math
import numbers
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KILL_SWITCH = Path(os.getenv("KILL_SWITCH_PATH", str(ROOT / "storage/AUTOMATION_OFF")))

# FR-04. The first four are labelled must_not_auto_respond on every ticket (evidence E13); data_residency is
# added because the Tier Two engineer says data-location mistakes become compliance problems (PRD decision 1).
MUST_ESCALATE = {"security_incident", "compliance_request", "feature_request", "unclear_request", "data_residency"}
ROUTE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.85"))
INTENT_MIN = float(os.getenv("INTENT_MIN_CONFIDENCE", "0.50"))


def is_score(x) -> bool:
    # numbers.Real, not (int, float): model outputs are often NumPy floats, which are not Python floats.
    return isinstance(x, numbers.Real) and not isinstance(x, bool) and math.isfinite(x)


def route(cls: dict, hits: list[dict], threshold: float = ROUTE_THRESHOLD, intent_min: float = INTENT_MIN) -> dict:
    def escalate(reason, reqs):
        return {"action": "escalate", "reason": reason, "threshold_applied": threshold, "requirement_ids": reqs}

    if KILL_SWITCH.exists():
        return escalate("Automated replies are switched off (kill switch); a person answers every ticket.",
                        ["GOV-KILL-SWITCH"])
    intent, conf, p = cls.get("intent", {}).get("value"), cls.get("intent", {}).get("confidence"), cls.get("p_auto")
    if not (is_score(conf) and is_score(p)):
        return escalate("No usable confidence score, so a person needs to answer.", ["FR-05", "GOV-CONFIDENCE-FLOOR"])
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
            return escalate(reason, reqs)
    return {"action": "auto_respond", "threshold_applied": threshold, "requirement_ids": ["FR-05"],
            "reason": f"Recognised as '{intent}' ({conf:.0%} confident), {p:.0%} likely answerable from "
                      f"{hits[0]['doc_id']}."}


def escalation_packet(text: str, cls: dict, hits: list[dict], uncertainty: str) -> dict:
    """What travels with an escalation so tier two need not re-ask the customer (FR-06)."""
    # shortcut: the summary is the ticket itself (median ~140 characters); add a model summary if tickets get long.
    return {"summary": text[:300] or "(empty ticket)",
            "likely_topic": {k: cls["intent"].get(k) for k in ("value", "confidence", "alternatives")},
            "articles": [h["chunk_id"] for h in hits[:3]],
            "uncertainty": uncertainty}
