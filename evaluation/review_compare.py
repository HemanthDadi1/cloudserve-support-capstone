"""Compare two PR-02 versions on the same drafted answers: how many would be released, per label group.

Same dev tickets as evaluation/prompt_compare.py. Each ticket is drafted once with the live PR-01, then
checked by both PR-02 versions. A better check releases as many "should answer" drafts and fewer
"should refuse" ones.

Usage: python -m evaluation.review_compare --baseline history/PR-02_grounding_v1.0.txt [--per-group 12]
"""
import argparse
from collections import Counter

from dotenv import load_dotenv

from evaluation.prompt_compare import candidate_groups
from src.generate import generate, passages_for
from src.llm import load_prompt
from src.retrieve import Retriever
from src.validate import PROMPT, validate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True, help="older PR-02 file, relative to prompts/")
    ap.add_argument("--per-group", type=int, default=12)
    a = ap.parse_args()
    load_dotenv()
    r = Retriever()
    versions = {"baseline": load_prompt(a.baseline), "current": PROMPT}
    print(f"{'group':14s} {'version':14s} drafted  released  blocked (reasons)")
    for g, items in candidate_groups(r).items():
        drafts = [(t, hits, generate(t, hits, r)) for t, hits in items[:a.per_group]]
        drafts = [(t, hits, d) for t, hits, d in drafts if d["status"] == "answered"]
        for name, prompt in versions.items():
            results = [validate(d["sentences"], t, passages_for(hits, r), prompt=prompt) for t, hits, d in drafts]
            why = Counter(k for v in results for k, c in v["checks"].items() if c == "fail")
            label = f"{name} v{prompt['version']}"
            print(f"{g:14s} {label:14s} {len(drafts):7d}  {sum(v['passed'] for v in results):8d}  "
                  f"{sum(not v['passed'] for v in results):7d} {dict(why)}", flush=True)


if __name__ == "__main__":
    main()
