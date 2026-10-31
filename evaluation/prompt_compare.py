"""Compare two PR-01 versions on dev tickets that could reach answer drafting.

Uses dev tickets (not validation) so prompt changes are not tuned on the evaluation set. Groups:
"should answer" (labelled auto_respond) and "should refuse" (labelled not answerable from the docs).
A better prompt refuses more of the second group without refusing the first.

Usage: python -m evaluation.prompt_compare --baseline history/PR-01_answer_v1.0.txt [--per-group 12]
"""
import argparse
import json
import random
from collections import Counter

from dotenv import load_dotenv

from src.generate import PROMPT, generate
from src.ingest import normalize
from src.llm import load_prompt
from src.retrieve import ROOT, Retriever
from src.route import MUST_ESCALATE


def candidate_groups(r: Retriever) -> dict:
    """Distinct dev tickets that could reach drafting, split by label and shuffled with a fixed seed."""
    seen, groups = set(), {"should answer": [], "should refuse": []}
    for raw in json.loads((ROOT / "data/development_tickets.json").read_text()):
        t = normalize(raw)
        if t.body in seen:
            continue
        seen.add(t.body)
        hits = r.search(t.text)
        lab = raw["labels"]
        # Not route(): the classifier was trained on these dev tickets, so in-sample it lets almost no
        # "not answerable" ticket through. Select tickets that could reach drafting on unseen data instead:
        # a passage passes the relevance threshold and the topic is not always escalated.
        if not hits or lab["intent"] in MUST_ESCALATE:
            continue
        key = "should answer" if lab["expected_route"] == "auto_respond" else \
            "should refuse" if not lab["answerable_from_docs"] else None
        if key:
            groups[key].append((t, hits))
    random.Random(7).shuffle(groups["should answer"])
    random.Random(7).shuffle(groups["should refuse"])
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True, help="older prompt file, relative to prompts/")
    ap.add_argument("--per-group", type=int, default=12)
    a = ap.parse_args()
    load_dotenv()
    r = Retriever()
    groups = candidate_groups(r)
    versions = {"baseline": load_prompt(a.baseline), "current": PROMPT}
    print("Distinct dev tickets reaching drafting: " + ", ".join(f"{k} {len(v)}" for k, v in groups.items()))
    print(f"{'group':14s} {'version':10s} answered  insufficient  other")
    for g, items in groups.items():
        for name, prompt in versions.items():
            n = Counter(generate(t, hits, r, prompt=prompt)["status"] for t, hits in items[:a.per_group])
            other = sum(v for k, v in n.items() if k not in ("answered", "insufficient"))
            label = f"{name} v{prompt['version']}"
            print(f"{g:14s} {label:10s} {n['answered']:8d}  {n['insufficient']:12d}  {other:5d}", flush=True)


if __name__ == "__main__":
    main()
