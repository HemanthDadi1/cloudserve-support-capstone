"""Validate: check every draft before release and block it on any failure (FR-08).

Checks run cheapest first: private data, forbidden commitments, then grounding with prompt PR-02.
Grounding fails closed: if it cannot run or its output is unusable, the draft is blocked.
The commitment patterns cover the three must_not_claim phrases in every reference answer
(a refund issued, a fix on our side, a delivery date) plus data-location promises (FR-04, Daniel).
"""
import json
import re

from src.ingest import Ticket
from src.llm import LLMUnavailable, complete, load_prompt, render

PROMPT = load_prompt("PR-02_grounding.txt")
PII = {
    "email address": r"[\w.+-]+@[\w-]+\.[\w.]+",
    "phone number": r"\+?\d[\d\s().-]{8,}\d",
    "key or token": r"\b(?:sk|pk|api|key|tok)[-_][A-Za-z0-9]{8,}|\b[A-Fa-f0-9]{32,}\b",
    "card number": r"\b(?:\d[ -]?){13,16}\b",
}
COMMITMENTS = {
    # Promises only: the billing articles explain refund policy ("applied ... rather than refunded"), which is allowed.
    "money": r"\b((?:refund|credit) (?:has been|was|will be|is being) (?:issued|processed|made|applied)|"
             r"(?:we|i)(?:'ll| will| have|'ve| can)? (?:issue|process|apply|give|arrange)\b[^.]{0,30}\b"
             r"(?:refund|credit|discount)|(?:we|i)(?:'ve| have)? (?:refunded|credited)|"
             r"you (?:will|'ll) (?:receive|get|be given) (?:a |an )?(?:full |partial )?(?:refund|credit|discount)|"
             r"waive[ds]? (?:the|your)|free of charge|compensat\w*)",
    "fix claim": r"\b(fixed on our (?:side|end)|we(?: have|'ve)? (?:fixed|resolved|deployed a fix)|"
                 r"(?:issue|problem|bug) (?:has been|was|is now) (?:fixed|resolved))\b",
    "delivery date": r"\b((?:will|should) be (?:fixed|available|released|shipped|deployed) (?:by|on|within|in|next)|"
                     r"\beta\b|by (?:next|the end of|monday|tuesday|wednesday|thursday|friday)|"
                     r"(?:january|february|march|april|may|june|july|august|september|october|november|december)"
                     r" \d{1,2})",
    "data location": r"\b((?:your|the) data (?:is|will be|are) (?:stored|hosted|kept|processed)|"
                     r"(?:stored|hosted|kept|processed) (?:only )?in (?:the )?"
                     r"(?:eu|europe|us|usa|united states|uk|asia|apac|region))\b",
}


def find_private(text: str, ticket: Ticket) -> list[str]:
    found = [kind for kind, p in PII.items() if re.search(p, text)]
    for label, value in (("customer name", ticket.customer_name), ("customer ID", ticket.customer_id)):
        if value and value.lower() in text.lower():
            found.append(label)
    return found


def find_commitments(text: str) -> list[str]:
    return [kind for kind, p in COMMITMENTS.items() if re.search(p, text, re.I)]


def check_grounding(sentences: list[dict], passages: list[dict], llm) -> tuple[str, list, str | None]:
    cited = {c for s in sentences for c in s["cite"]}
    user = render(PROMPT["user"],
                  passages="\n".join(f'<passage id="{p["chunk_id"]}">{p["text"]}</passage>'
                                     for p in passages if p["chunk_id"] in cited),
                  sentences="\n".join(f"{i}. {s['text']} (cites: {', '.join(s['cite'])})"
                                      for i, s in enumerate(sentences)))
    try:
        res = llm(PROMPT["system"], user)
        verdicts = [r["verdict"] for r in json.loads(res["content"])["results"]]
    except LLMUnavailable:
        return "fail", [], None
    except (ValueError, KeyError, TypeError):
        return "fail", [], res.get("model")
    if len(verdicts) != len(sentences) or not set(verdicts) <= {"supported", "unsupported", "no_claim"}:
        return "fail", verdicts, res.get("model")
    return ("fail" if "unsupported" in verdicts else "pass"), verdicts, res["model"]


def validate(sentences: list[dict], ticket: Ticket, passages: list[dict], llm=complete) -> dict:
    text = " ".join(s["text"] for s in sentences)
    private, commitments = find_private(text, ticket), find_commitments(text)
    out = {"prompt_version": f"{PROMPT['id']} v{PROMPT['version']}", "model": None, "verdicts": [],
           "found": {"private": private, "commitments": commitments},
           "checks": {"pii": "fail" if private else "pass", "commitments": "fail" if commitments else "pass",
                      "grounding": "skipped"}}
    if not (private or commitments):  # skip the model call when the draft is already blocked
        out["checks"]["grounding"], out["verdicts"], out["model"] = check_grounding(sentences, passages, llm)
    reasons = ([f"private data ({', '.join(private)})"] if private else []) + \
              ([f"forbidden commitment ({', '.join(commitments)})"] if commitments else [])
    if out["checks"]["grounding"] == "fail":
        reasons.append("a sentence is not supported by its sources" if "unsupported" in out["verdicts"]
                       else "grounding could not be checked")
    out["passed"] = not reasons
    out["blocked_reason"] = "; ".join(reasons) or None
    return out
