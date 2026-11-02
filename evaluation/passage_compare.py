"""Paired comparison: draft answers from the topic-expanded search (A) or the plain search (B).

Same dev tickets both ways: every distinct dev ticket that out-of-fold routing sends to drafting. Each is
drafted and checked with both passage sets; the better version releases more answers without more replies
to tickets labelled not answerable. Dev only, so the validation set stays untouched.

Usage: python -m evaluation.passage_compare [--limit N]
"""
import argparse
import json
from collections import Counter

from dotenv import load_dotenv

from evaluation.routing_threshold import out_of_fold
from src.generate import generate, passages_for
from src.ingest import normalize
from src.retrieve import ROOT, Retriever
from src.route import route
from src.validate import validate


def outcome(t, hits, r) -> dict:
    g = generate(t, hits, r)
    if g["status"] != "answered":
        return {"result": g["status"]}
    v = validate(g["sentences"], t, passages_for(hits, r))
    exp = set(t.raw["labels"]["expected_doc_ids"])
    cites = [c.split("#")[0] for s in g["sentences"] for c in s["cite"]]
    return {"result": "sent" if v["passed"] else "blocked", "to_unanswerable": v["passed"] and not exp,
            "cites": len(cites) if v["passed"] else 0, "cites_ok": sum(c in exp for c in cites) if v["passed"] else 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    load_dotenv()
    r = Retriever()
    T = [normalize(t) for t in json.loads((ROOT / "data/development_tickets.json").read_text())]
    o = out_of_fold(T, r)
    seen, picked = set(), []
    for i, t in enumerate(T):
        cls = {"fallback": False, "p_auto": o["p_auto"][i],
               "intent": {"value": o["intent"][i], "confidence": o["iconf"][i]}}
        if t.body not in seen and route(cls, o["hits"][i])["action"] == "auto_respond":
            seen.add(t.body)
            picked.append((t, o["agent_hits"][i]))
    picked = picked[:a.limit] if a.limit else picked
    print(f"{len(picked)} distinct dev tickets reach drafting", flush=True)
    totals = {}
    for name, hits_of in [("A expanded", lambda t, h: h), ("B plain", lambda t, h: r.search(t.text))]:
        res = [outcome(t, hits_of(t, h), r) for t, h in picked]
        n = Counter(x["result"] for x in res)
        c, ok = sum(x.get("cites", 0) for x in res), sum(x.get("cites_ok", 0) for x in res)
        totals[name] = (n["sent"], n["blocked"], sum(x.get("to_unanswerable", False) for x in res), ok / max(c, 1))
        other = sum(n.values()) - n["sent"] - n["blocked"]
        print(f"{name:11s} sent {n['sent']:3d} | blocked {n['blocked']:3d} | other {other:3d} "
              f"| sent to unanswerable {totals[name][2]:3d} | citation accuracy {totals[name][3]:.1%}", flush=True)


if __name__ == "__main__":
    main()
