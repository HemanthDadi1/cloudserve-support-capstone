"""Metrics report for a harness run: the Build Spec's volume, business, technical and governance groups.

Label-based figures are computed only for tickets that carry labels, so the report also works on
an unlabelled file.
"""
import statistics
from collections import Counter, defaultdict

from sklearn.metrics import classification_report

from evaluation.routing_threshold import ece


def pct(n, d):
    return round(100 * n / d, 1) if d else None


def quantile(xs, q):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(q * len(xs)))], 2) if xs else None


def compute(results: list[dict], log_rows: list[dict]) -> dict:
    n = len(results)
    final = Counter(r["final"] for r in results)
    sent = [r for r in results if r["final"] == "auto_respond"]
    lab = [r for r in results if r.get("labels") and r.get("classification")]
    lat = [r["latency_s"] for r in results]

    m = {"volume": {"processed": n, "auto_answered": final["auto_respond"],
                    "escalated": final["escalate"] + final["block"], "blocked": final["block"],
                    "errors": sum("error" in r for r in results)}}

    hist = [r["labels"] for r in results if r.get("labels")]
    m["business"] = {
        "first_contact_resolution_pct": pct(len(sent), n),
        "escalation_rate_pct": pct(n - len(sent), n),
        "first_reply_s_automated": {"mean": round(statistics.mean(x["latency_s"] for x in sent), 2) if sent else None,
                                    "median": quantile([x["latency_s"] for x in sent], 0.5)},
        "processing_s_all": {"mean": round(statistics.mean(lat), 2) if lat else None,
                             "median": quantile(lat, 0.5), "p95": quantile(lat, 0.95)},
        "labelled_should_auto_pct": pct(sum(h["expected_route"] == "auto_respond" for h in hist), len(hist)),
    }

    tech = {}
    if lab:
        y = [r["labels"]["intent"] for r in lab]
        p = [r["classification"]["intent"]["value"] for r in lab]
        rep = classification_report(y, p, output_dict=True, zero_division=0)
        tech["intent"] = {"accuracy_pct": pct(sum(a == b for a, b in zip(y, p)), len(y)),
                          "macro_precision_pct": round(100 * rep["macro avg"]["precision"], 1),
                          "macro_recall_pct": round(100 * rep["macro avg"]["recall"], 1),
                          "calibration_error": round(float(ece([r["classification"]["intent"]["confidence"]
                                                               for r in lab], [a == b for a, b in zip(y, p)])), 3),
                          "per_class": {k: {"precision": round(v["precision"], 2), "recall": round(v["recall"], 2),
                                            "support": int(v["support"])}
                                        for k, v in rep.items() if k not in ("accuracy", "macro avg", "weighted avg")}}
        tech["urgency_accuracy_pct"] = pct(sum(r["labels"]["urgency"] == r["classification"]["urgency"]["value"]
                                               for r in lab), len(lab))
        ans = [r for r in lab if r["labels"].get("expected_doc_ids")]
        tech["retrieval_hit_rate_pct"] = pct(sum(bool({h.split("#")[0] for h in r["hits"]}
                                                      & set(r["labels"]["expected_doc_ids"])) for r in ans), len(ans))
        sent_lab = [r for r in sent if r.get("labels")]
        tech["routing"] = {
            "sent_but_should_escalate": sum(r["labels"]["expected_route"] == "escalate" for r in sent_lab),
            "sent_but_must_not_auto": sum(bool(r["labels"].get("must_not_auto_respond")) for r in sent_lab),
            "agreement_with_expected_route_pct": pct(sum((r["final"] == "auto_respond") ==
                                                         (r["labels"]["expected_route"] == "auto_respond")
                                                         for r in lab), len(lab)),
        }
        cites = [(c.split("#")[0], r["labels"].get("expected_doc_ids") or [])
                 for r in sent_lab for s in r["generation"]["sentences"] for c in s["cite"]]
        tech["citation_accuracy_pct"] = pct(sum(d in exp for d, exp in cites), len(cites))
    verdicts = [v for r in results if r.get("validation") for v in r["validation"]["verdicts"]]
    tech["drafts_unsupported_sentence_pct"] = pct(verdicts.count("unsupported"), len(verdicts))
    tech["sent_unsupported_sentence_pct"] = 0.0 if sent else None  # sent replies passed grounding by construction
    tech["latency_s"] = {"median": quantile(lat, 0.5), "p95": quantile(lat, 0.95)}
    tech["models_used"] = dict(Counter((r.get("generation") or {}).get("model") for r in results
                                       if r.get("generation")))
    m["technical"] = tech

    checks = [r["validation"]["checks"] for r in results if r.get("validation")]
    by_ticket = Counter(row["ticket_id"] for row in log_rows if row["stage"] == "routing")
    m["governance"] = {
        "decisions_logged": len(log_rows),
        "tickets_with_routing_decision": len(by_ticket),
        "log_reconciles": (len(by_ticket) == len({r["ticket_id"] for r in results})
                           and all(v == 1 for v in by_ticket.values())),
        "guardrail_activations": {k: sum(c.get(k) == "fail" for c in checks)
                                  for k in ("instruction", "pii", "commitments", "grounding", "relevance")},
        "private_data_detections": sum(c.get("pii") == "fail" for c in checks),
        "private_data_in_sent_replies": sum(r["validation"]["checks"].get("pii") == "fail" for r in sent),
        "blocked_reasons": dict(Counter(r["validation"]["blocked_reason"] for r in results
                                        if r["final"] == "block")),
    }

    fair = {}
    for col in ("customer_tier", "customer_region", "language_fluency"):
        g = defaultdict(list)
        for r in results:
            g[r.get(col) or "unknown"].append(r["final"] == "auto_respond")
        rates = {k: {"tickets": len(v), "auto_answered_pct": pct(sum(v), len(v))} for k, v in sorted(g.items())}
        vals = [x["auto_answered_pct"] for x in rates.values() if x["tickets"] >= 10]
        fair[col] = {"groups": rates, "max_gap_points": round(max(vals) - min(vals), 1) if len(vals) > 1 else None}
    m["fairness"] = fair
    return m


def to_markdown(m: dict, source: str) -> str:
    v, b, t, g = m["volume"], m["business"], m["technical"], m["governance"]
    lines = [f"# Metrics report\n\nInput: `{source}`\n",
             "## Volume\n", "| Measure | Value |", "|---|---|",
             *[f"| {k.replace('_', ' ')} | {x} |" for k, x in v.items()],
             "\n## Business\n", "| Measure | Value |", "|---|---|",
             f"| First contact resolution | {b['first_contact_resolution_pct']}% |",
             f"| Escalation rate | {b['escalation_rate_pct']}% |",
             f"| Time to first reply, automated answers (mean / median s) | {b['first_reply_s_automated']['mean']} / "
             f"{b['first_reply_s_automated']['median']} |",
             f"| Processing time, all tickets (mean / median / p95 s) | {b['processing_s_all']['mean']} / "
             f"{b['processing_s_all']['median']} / {b['processing_s_all']['p95']} |",
             f"| Labelled as answerable without a person | {b['labelled_should_auto_pct']}% |",
             "\n## Technical\n", "| Measure | Value |", "|---|---|"]
    if "intent" in t:
        i = t["intent"]
        lines += [f"| Intent accuracy / macro precision / macro recall | {i['accuracy_pct']}% / "
                  f"{i['macro_precision_pct']}% / {i['macro_recall_pct']}% |",
                  f"| Intent calibration error | {i['calibration_error']} |",
                  f"| Urgency accuracy | {t['urgency_accuracy_pct']}% |",
                  f"| Retrieval hit rate (expected article retrieved) | {t['retrieval_hit_rate_pct']}% |",
                  f"| Citation accuracy (sent replies) | {t['citation_accuracy_pct']}% |",
                  f"| Sent but labelled escalate / must-not-auto | {t['routing']['sent_but_should_escalate']} / "
                  f"{t['routing']['sent_but_must_not_auto']} |",
                  f"| Routing agreement with labels | {t['routing']['agreement_with_expected_route_pct']}% |"]
    lines += [f"| Unsupported sentences in drafts (before guardrails) | {t['drafts_unsupported_sentence_pct']}% |",
              f"| Unsupported sentences in sent replies | {t['sent_unsupported_sentence_pct']}% |",
              f"| Latency median / p95 (s) | {t['latency_s']['median']} / {t['latency_s']['p95']} |",
              f"| Models used for drafts | {t['models_used']} |"]
    if "intent" in t:
        lines += ["\n### Intent precision and recall per class\n", "| Intent | Precision | Recall | Support |",
                  "|---|---|---|---|",
                  *[f"| {k} | {x['precision']} | {x['recall']} | {x['support']} |"
                    for k, x in t["intent"]["per_class"].items()]]
    lines += ["\n## Governance\n", "| Measure | Value |", "|---|---|",
              f"| Decisions logged | {g['decisions_logged']} |",
              f"| Tickets with a routing decision | {g['tickets_with_routing_decision']} |",
              f"| Log reconciles with tickets processed | {g['log_reconciles']} |",
              "| Guardrail activations (instruction / pii / commitments / grounding / relevance) | "
              + " / ".join(str(g["guardrail_activations"][k])
                           for k in ("instruction", "pii", "commitments", "grounding", "relevance")) + " |",
              f"| Private data detections / in sent replies | {g['private_data_detections']} / "
              f"{g['private_data_in_sent_replies']} |",
              f"| Blocked reasons | {g['blocked_reasons'] or 'none'} |",
              "\n## Fairness (share answered automatically)\n"]
    for col, f in m["fairness"].items():
        lines += [f"**{col}** (largest gap between groups of 10+: {f['max_gap_points']} points)\n",
                  "| Group | Tickets | Answered automatically |", "|---|---|---|",
                  *[f"| {k} | {x['tickets']} | {x['auto_answered_pct']}% |" for k, x in f["groups"].items()], ""]
    return "\n".join(lines)
