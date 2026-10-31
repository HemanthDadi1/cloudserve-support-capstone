"""Validate: check every draft before release and block it on any failure (FR-08, FR-13).

Checks run cheapest first: private data, forbidden commitments, then prompt PR-02, which judges grounding
and (from v1.1) whether the ticket needs a person anyway. Both fail closed: if PR-02 cannot run or its
output is unusable, the draft is blocked.
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
# Instruction integrity (Governance Framework section 4): a ticket that tries to instruct the system is blocked
# and recorded for review, even though PR-01 already treats ticket text as data. None of the 580 dev and
# validation tickets match these patterns.
INJECTION = (r"\b(ignore|disregard|forget|override)\b[^.]{0,40}\b(instructions?|rules|prompt|guidelines)\b|"
             r"\b(system|developer|hidden) prompt\b|\byou are now\b|\b(admin|developer|god|jailbreak) mode\b|"
             r"\b(reveal|print|show|repeat)\b[^.]{0,30}\b(prompt|instructions)\b|\bact as\b|\bpretend (to be|you)\b")


def find_injection(text: str) -> list[str]:
    return [m.group(0) for m in re.finditer(INJECTION, text, re.I)]


def find_private(text: str, ticket: Ticket) -> list[str]:
    found = [kind for kind, p in PII.items() if re.search(p, text)]
    for label, value in (("customer name", ticket.customer_name), ("customer ID", ticket.customer_id)):
        if value and value.lower() in text.lower():
            found.append(label)
    return found


def find_commitments(text: str) -> list[str]:
    return [kind for kind, p in COMMITMENTS.items() if re.search(p, text, re.I)]


def review(sentences: list[dict], ticket: Ticket, passages: list[dict], llm, prompt: dict) -> dict:
    """PR-02: grounding per sentence (FR-08) and, from v1.1, whether the ticket needs a person anyway (FR-13).
    Fails closed: unavailable or malformed output fails every check it should have answered."""
    asks_relevance = "{ticket}" in prompt["user"]
    cited = {c for s in sentences for c in s["cite"]}
    user = render(prompt["user"], ticket=ticket.text.replace("</ticket>", ""),
                  passages="\n".join(f'<passage id="{p["chunk_id"]}">{p["text"]}</passage>'
                                     for p in passages if p["chunk_id"] in cited),
                  sentences="\n".join(f"{i}. {s['text']} (cites: {', '.join(s['cite'])})"
                                      for i, s in enumerate(sentences)))
    out = {"grounding": "fail", "relevance": "fail" if asks_relevance else "skipped", "verdicts": [], "model": None,
           "needs_person_reason": None}
    try:
        res = llm(prompt["system"], user)
    except LLMUnavailable:
        return out
    out["model"] = res["model"]
    try:
        body = json.loads(res["content"])
        out["verdicts"] = [r["verdict"] for r in body["results"]]
        needs = body.get("needs_person")
    except (ValueError, KeyError, TypeError):
        return out
    if len(out["verdicts"]) == len(sentences) and set(out["verdicts"]) <= {"supported", "unsupported", "no_claim"}:
        out["grounding"] = "fail" if "unsupported" in out["verdicts"] else "pass"
    if asks_relevance and isinstance(needs, bool):
        out["relevance"] = "fail" if needs else "pass"
        out["needs_person_reason"] = body.get("needs_person_reason") if needs else None
    return out


def validate(sentences: list[dict], ticket: Ticket, passages: list[dict], llm=complete, prompt: dict = PROMPT) -> dict:
    text = " ".join(s["text"] for s in sentences)
    private, commitments, injection = find_private(text, ticket), find_commitments(text), find_injection(ticket.text)
    out = {"prompt_version": f"{prompt['id']} v{prompt['version']}", "model": None, "verdicts": [],
           "found": {"private": private, "commitments": commitments, "injection": injection},
           "needs_person_reason": None,
           "checks": {"instruction": "fail" if injection else "pass", "pii": "fail" if private else "pass",
                      "commitments": "fail" if commitments else "pass", "grounding": "skipped", "relevance": "skipped"}}
    if not (private or commitments or injection):  # skip the model call when the draft is already blocked
        r = review(sentences, ticket, passages, llm, prompt)
        out["checks"]["grounding"], out["checks"]["relevance"] = r["grounding"], r["relevance"]
        out["verdicts"], out["model"], out["needs_person_reason"] = r["verdicts"], r["model"], r["needs_person_reason"]
    reasons = ([f"the ticket tries to instruct the system ({'; '.join(injection)})"] if injection else []) + \
              ([f"private data ({', '.join(private)})"] if private else []) + \
              ([f"forbidden commitment ({', '.join(commitments)})"] if commitments else [])
    if out["checks"]["grounding"] == "fail":
        reasons.append("a sentence is not supported by its sources" if "unsupported" in out["verdicts"]
                       else "grounding could not be checked")
    if out["checks"]["relevance"] == "fail":
        reasons.append(f"the ticket needs a person ({out['needs_person_reason']})" if out["needs_person_reason"]
                       else "relevance could not be checked")
    out["passed"] = not reasons
    out["blocked_reason"] = "; ".join(reasons) or None
    return out
