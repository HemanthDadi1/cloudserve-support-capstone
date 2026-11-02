"""Fairness audit (Governance Framework section 3): outcomes by customer segment, with sample sizes and tests.

Part A uses all dev tickets with out-of-fold routing (each ticket routed by models that never saw its
wording), so every segment has enough tickets and no model calls are needed. Part B uses the replies
actually sent in a harness run (small: quality figures there are indicative only).

Usage: python -m evaluation.fairness [--results evaluation/results/results.jsonl] [--output evaluation/fairness.md]
"""
import argparse
import json
import statistics
from pathlib import Path

import numpy as np
from scipy.stats import chi2_contingency

from discovery.evidence import table
from evaluation.routing_threshold import out_of_fold
from src.ingest import normalize
from src.retrieve import ROOT, Retriever
from src.route import route

import pandas as pd


def segment_columns(df: pd.DataFrame, median_len: float) -> dict:
    return {"plan": df.customer_tier, "fluency": df.language_fluency, "region": df.customer_region,
            "length": np.where(df.length <= median_len, "short", "long")}


def p_value(df: pd.DataFrame, seg, col: str) -> str:
    """Chi-square test that the rate of `col` is the same in every segment (p < 0.05: a real difference)."""
    sub = df[col].notna()
    t = pd.crosstab(np.asarray(seg)[sub], df.loc[sub, col])
    if t.shape[1] < 2 or t.shape[0] < 2:
        return "n/a"
    p = chi2_contingency(t)[1]
    return f"{p:.3f}" + (" *" if p < 0.05 else "")


def part_a(tickets) -> tuple[str, pd.DataFrame]:
    o = out_of_fold(tickets, Retriever())
    rows = []
    for i, t in enumerate(tickets):
        lab = t.raw["labels"]
        cls = {"fallback": False, "p_auto": o["p_auto"][i],
               "intent": {"value": o["intent"][i], "confidence": o["iconf"][i]}}
        auto = route(cls, o["hits"][i])["action"] == "auto_respond"
        should_auto = lab["expected_route"] == "auto_respond"
        exp = set(lab["expected_doc_ids"])
        found = {h["doc_id"] for h in o["hits"][i]}
        given = ({h["doc_id"] for h in o["agent_hits"][i]}  # what the agent receives on an escalation
                 | ({o["topic_article"][i]} if o["topic_article"][i] else set()))
        rows.append({"customer_tier": t.customer_tier, "language_fluency": t.language_fluency,
                     "customer_region": t.customer_region, "length": len(t.text),
                     "answered": auto, "route_correct": auto == should_auto,
                     "unsafe_send": (auto and not should_auto) if auto else None,
                     "retrieval_hit": bool(exp & found) if exp else None,
                     "agent_has_article": bool(exp & given) if exp else None,
                     "intent_correct": o["intent"][i] == lab["intent"]})
    df = pd.DataFrame(rows)
    med = statistics.median(df.length)
    out = [f"## Part A: all {len(df)} dev tickets, out-of-fold routing\n",
           f"Short = {int(med)} characters or fewer (the median). Rates in %. p-value: chi-square test that the rate "
           "is equal across the segments in that family; * marks p < 0.05 (a difference unlikely to be noise).\n"]
    for fam, seg in segment_columns(df, med).items():
        g = df.groupby(seg)
        tab = pd.DataFrame({
            "tickets": g.size(),
            "answered automatically": (100 * g.answered.mean()).round(1),
            "routing correct": (100 * g.route_correct.mean()).round(1),
            "sends that should have escalated": g.unsafe_send.apply(
                lambda s: f"{int(s.dropna().sum())}/{int(s.notna().sum())}"),
            "retrieval hit (answerable)": g.retrieval_hit.apply(lambda s: round(100 * s.dropna().mean(), 1)),
            "article available to agent": g.agent_has_article.apply(lambda s: round(100 * s.dropna().mean(), 1)),
            "intent accuracy": (100 * g.intent_correct.mean()).round(1),
        })
        tab["routing gap from best (points)"] = (tab["routing correct"].max() - tab["routing correct"]).round(1)
        tab.index.name = fam
        out += [f"### By {fam}\n", table(tab), "",
                "p-values: answered " + p_value(df, seg, "answered") + "; routing correct " +
                p_value(df, seg, "route_correct") + "; retrieval hit " + p_value(df, seg, "retrieval_hit") +
                "; article available " + p_value(df, seg, "agent_has_article") +
                "; intent " + p_value(df, seg, "intent_correct") + "\n"]
    return "\n".join(out), df


def part_b(results_path: Path, median_len: float) -> str:
    if not results_path.exists():
        return "## Part B: no harness results found\n"
    R = [json.loads(line) for line in results_path.read_text().splitlines()]
    rows = []
    for r in R:
        lab, g = r.get("labels") or {}, r.get("generation") or {}
        sent = r["final"] == "auto_respond"
        cites = [c.split("#")[0] for s in g.get("sentences") or [] for c in s["cite"]] if sent else []
        exp = set(lab.get("expected_doc_ids") or [])
        rows.append({"customer_tier": r["customer_tier"], "language_fluency": r["language_fluency"],
                     "customer_region": r["customer_region"],
                     "length": len((r.get("packet") or {}).get("summary") or "") or median_len,
                     "sent": r["final"] == "auto_respond", "drafted": bool(g),
                     "blocked": r["final"] == "block",
                     "sent_to_unanswerable": r["final"] == "auto_respond" and not exp,
                     "cites": len(cites), "cites_ok": sum(c in exp for c in cites)})
    df = pd.DataFrame(rows)
    shown = results_path.resolve().relative_to(ROOT) if results_path.resolve().is_relative_to(ROOT) else results_path
    out = [f"## Part B: replies sent in `{shown}` ({int(df.sent.sum())} sent of {len(df)})\n",
           "Too few replies per segment for tests; read as indicative only.\n"]
    for fam, seg in segment_columns(df, median_len).items():
        if fam == "length":
            continue  # results.jsonl keeps the full text only for escalations
        g = df.groupby(seg)
        tab = pd.DataFrame({"tickets": g.size(), "drafted": g.drafted.sum(), "sent": g.sent.sum(),
                            "blocked": g.blocked.sum(), "sent to unanswerable": g.sent_to_unanswerable.sum(),
                            "citation accuracy %":
                                (100 * g.cites_ok.sum() / g.cites.sum().replace(0, np.nan)).round(1)})
        tab.index.name = fam
        out += [f"### By {fam}\n", table(tab), ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickets", default=ROOT / "data/development_tickets.json")
    ap.add_argument("--results", default=ROOT / "evaluation/results/results.jsonl")
    ap.add_argument("--output", default=ROOT / "evaluation/fairness.md")
    a = ap.parse_args()
    tickets = [normalize(t) for t in json.loads(Path(a.tickets).read_text())]
    text_a, df = part_a(tickets)
    md = ("# Fairness audit\n\nGenerated by `python -m evaluation.fairness`. Figures only; interpretation "
          "belongs in the governance framework.\n\n" + text_a + "\n"
          + part_b(Path(a.results), statistics.median(df.length)))
    Path(a.output).write_text(md)
    print(f"wrote {a.output}")


if __name__ == "__main__":
    main()
