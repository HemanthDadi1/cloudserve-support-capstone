"""Generate: draft a cited answer from retrieved passages with prompt PR-01 (FR-07), label it (FR-09).

Anything but a well-formed answer whose every citation was actually provided comes back with a status
other than "answered", and the caller escalates it.
"""
import json
import re

from src.ingest import Ticket
from src.llm import LLMUnavailable, complete, load_prompt, render

PROMPT = load_prompt("PR-01_answer.txt")
LABEL = 'This reply was drafted automatically from our documentation. Reply "agent" to reach a person.'


def passages_for(hits: list[dict], retriever) -> list[dict]:
    """Retrieved passages plus each article's Resolution section: search usually matches Symptoms,
    but the steps a customer needs are in Resolution."""
    ids = [h["chunk_id"] for h in hits]
    for h in hits:
        res = f"{h['doc_id']}#resolution"
        if res not in ids and retriever.passage(res):
            ids.append(res)
    return [retriever.passage(i) for i in ids]


def parse(raw: str, allowed: set[str]) -> dict | None:
    """The model's JSON if it matches PR-01's contract and cites only allowed passages, else None."""
    try:
        out = json.loads(re.sub(r"^```(?:json)?|```$", "", raw.strip()).strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(out, dict) or out.get("status") not in ("answered", "insufficient"):
        return None
    sentences = out.get("sentences") or []
    for s in sentences:
        if not (isinstance(s, dict) and isinstance(s.get("text"), str) and s["text"].strip()
                and isinstance(s.get("cite"), list) and s["cite"] and set(s["cite"]) <= allowed):
            return None
    if out["status"] == "answered" and not sentences:
        return None
    return {"status": out["status"], "sentences": sentences if out["status"] == "answered" else []}


def generate(ticket: Ticket, hits: list[dict], retriever, llm=complete) -> dict:
    passages = passages_for(hits, retriever)
    user = render(PROMPT["user"], ticket=ticket.text.replace("</ticket>", ""),
                  passages="\n".join(f'<passage id="{p["chunk_id"]}">{p["text"]}</passage>' for p in passages))
    base = {"prompt_version": f"{PROMPT['id']} v{PROMPT['version']}", "passages": [p["chunk_id"] for p in passages]}
    try:
        raw = llm(PROMPT["system"], user)
    except LLMUnavailable as e:
        return {**base, "status": "unavailable", "sentences": [], "error": str(e)}
    return {**base, **(parse(raw, set(base["passages"])) or {"status": "invalid", "sentences": [], "raw": raw[:500]})}


def reply_text(sentences: list[dict]) -> str:
    return " ".join(s["text"].strip() for s in sentences) + "\n\n" + LABEL
