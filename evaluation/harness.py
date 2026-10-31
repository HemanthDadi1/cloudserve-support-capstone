"""Run every ticket in a file through the full pipeline, unattended, and write a metrics report (FR-12, A9, A10).

Usage: python -m evaluation.harness --input data/validation_tickets.json --output evaluation/results/

Every ticket ends as a sent answer or a logged escalation; an unexpected error on one ticket escalates
that ticket and the run continues. Output directory: results.jsonl (one line per ticket, written as it
goes), decisions.db (the decision log), metrics.json and metrics.md.
"""
import argparse
import json
import time
import traceback
from pathlib import Path

from dotenv import load_dotenv

from evaluation.metrics import compute, to_markdown
from src.classify import Classifier
from src.decision_log import DecisionLog
from src.generate import generate, passages_for, reply_text
from src.ingest import normalize
from src.llm import complete
from src.retrieve import Retriever
from src.route import KILL_SWITCH, escalation_packet, route
from src.validate import find_injection, validate

MODEL = "all-MiniLM-L6-v2 + LogisticRegression"


def process(t, retriever, classifier, log, llm) -> dict:
    cls = classifier.classify(t)
    hits = retriever.search(t.text)
    injection = find_injection(t.text)
    if injection:  # instruction integrity: block and record every attempt, whatever routing would decide
        reason = f"The ticket tries to instruct the system ({'; '.join(injection)}); recorded for review."
        d = {"action": "block", "reason": reason, "threshold_applied": None,
             "requirement_ids": ["GOV-INSTRUCTION-INTEGRITY"]}
    else:
        d = route(cls, hits)
    common = {"ticket_id": t.ticket_id, "input_summary": t.text[:200]}
    log.write(**common, stage="routing", model={"name": MODEL, "version": classifier.version},
              prediction={"value": cls["intent"]["value"], "confidence": cls["intent"]["confidence"],
                          "p_auto": cls["p_auto"], "urgency": cls["urgency"]["value"]},
              alternatives=cls["intent"]["alternatives"],
              sources_used=[{"doc_id": h["chunk_id"], "score": h["score"]} for h in hits],
              threshold_applied=d["threshold_applied"], action_taken=d["action"], reason=d["reason"],
              guardrail_results={"instruction": "fail"} if injection else None,
              requirement_ids=d["requirement_ids"] + ["FR-10"])
    out = {"classification": cls, "route": d, "hits": [h["chunk_id"] for h in hits], "generation": None,
           "validation": None}
    if injection:
        out["validation"] = {"checks": {"instruction": "fail"}, "verdicts": [], "blocked_reason": reason,
                             "found": {"injection": injection}}
        return {**out, "final": "block", "packet": escalation_packet(t.text, cls, hits, f"Blocked: {reason}")}
    if d["action"] == "escalate":
        return {**out, "final": "escalate", "packet": escalation_packet(t.text, cls, hits, d["reason"])}

    g = generate(t, hits, retriever, llm=llm)
    out["generation"] = {k: g.get(k) for k in ("status", "sentences", "model", "prompt_version", "error")}
    if g["status"] != "answered":
        reason = {"insufficient": "The documentation does not answer this ticket.",
                  "unavailable": "The model provider is unavailable, so a person needs to answer.",
                  "invalid": "The drafted answer did not meet the output contract."}[g["status"]]
        log.write(**common, stage="generation", model={"name": g.get("model"), "version": g["prompt_version"]},
                  prediction={"value": g["status"]}, action_taken="escalate", reason=reason,
                  prompt_version=g["prompt_version"], requirement_ids=["FR-07", "FR-11", "FR-10"])
        return {**out, "final": "escalate", "packet": escalation_packet(t.text, cls, hits, reason)}

    v = validate(g["sentences"], t, passages_for(hits, retriever), llm=llm)
    out["validation"] = v
    action = "auto_respond" if v["passed"] else "block"
    log.write(**common, stage="validation", model={"name": v["model"], "version": v["prompt_version"]},
              prediction={"value": "passed" if v["passed"] else "blocked"},
              sources_used=[{"doc_id": c} for s in g["sentences"] for c in s["cite"]],
              action_taken=action, reason=v["blocked_reason"] or "All release checks passed.",
              guardrail_results=v["checks"], prompt_version=v["prompt_version"],
              requirement_ids=["FR-08", "FR-10"] + (["FR-09"] if v["passed"] else []))
    if v["passed"] and KILL_SWITCH.exists():  # switched off while this ticket was being drafted
        reason = "Automated replies were switched off (kill switch) before this reply was sent."
        log.write(**common, stage="validation", action_taken="escalate", reason=reason,
                  requirement_ids=["GOV-KILL-SWITCH", "FR-10"])
        return {**out, "final": "escalate", "packet": escalation_packet(t.text, cls, hits, reason)}
    if v["passed"]:
        return {**out, "final": "auto_respond", "reply": reply_text(g["sentences"])}
    return {**out, "final": "block", "packet": escalation_packet(t.text, cls, hits, f"Blocked: {v['blocked_reason']}")}


def run(input_path: str, output_dir: str, llm=complete, limit: int | None = None) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("results.jsonl", "decisions.db"):
        (out / name).unlink(missing_ok=True)
    records = json.loads(Path(input_path).read_text())
    records = records[:limit] if limit else records
    retriever = Retriever()
    classifier = Classifier(retriever.model)
    log = DecisionLog(f"sqlite:///{(out / 'decisions.db').resolve()}")
    results = []
    with open(out / "results.jsonl", "w") as f:
        for i, raw in enumerate(records):
            t = normalize(raw, fallback_id=f"ROW-{i}")
            t0 = time.time()
            try:
                r = process(t, retriever, classifier, log, llm)
            except Exception as e:  # one bad ticket must never stop the run (A9)
                reason = f"Internal error ({type(e).__name__}); a person needs to handle this ticket."
                log.write(ticket_id=t.ticket_id, stage="routing", input_summary=t.text[:200], action_taken="escalate",
                          reason=reason, requirement_ids=["FR-11", "FR-10"])
                r = {"final": "escalate", "error": traceback.format_exc(limit=3),
                     "packet": {"summary": t.text[:300], "uncertainty": reason}}
            r = {"ticket_id": t.ticket_id, "channel": t.channel, "customer_tier": t.customer_tier,
                 "customer_region": t.customer_region, "language_fluency": t.language_fluency,
                 "labels": raw.get("labels") if isinstance(raw, dict) else None,
                 "latency_s": round(time.time() - t0, 3), **r}
            results.append(r)
            f.write(json.dumps(r) + "\n")
            f.flush()
            print(f"[{i + 1}/{len(records)}] {t.ticket_id} -> {r['final']} ({r['latency_s']:.1f}s)", flush=True)
    m = compute(results, log.rows())
    (out / "metrics.json").write_text(json.dumps(m, indent=2))
    (out / "metrics.md").write_text(to_markdown(m, input_path))
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", required=True, help="ticket file (JSON list, same schema as the dev set)")
    ap.add_argument("--output", required=True, help="directory for results, decision log and metrics")
    ap.add_argument("--limit", type=int, help="process only the first N tickets (smoke runs)")
    a = ap.parse_args()
    load_dotenv()
    m = run(a.input, a.output, limit=a.limit)
    v = m["volume"]
    print(f"\nDone: {v['processed']} tickets, {v['auto_answered']} answered, {v['escalated']} escalated, "
          f"{v['blocked']} blocked. Report: {Path(a.output) / 'metrics.md'}")


if __name__ == "__main__":
    main()
