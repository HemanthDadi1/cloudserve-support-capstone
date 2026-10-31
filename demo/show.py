"""Print a harness run's results readably, for the demo video: what came in, what was decided, and why.

Usage: python demo/show.py demo/out/results.jsonl
"""
import json
import sys
import textwrap

for r in map(json.loads, open(sys.argv[1] if len(sys.argv) > 1 else "demo/out/results.jsonl")):
    p = r.get("packet") or {}
    why = (r.get("validation") or {}).get("blocked_reason") or (r.get("route") or {}).get("reason") or ""
    print(f"\n=== {r['ticket_id']}  [{r['channel']}]  ->  {r['final'].upper()}")
    print("  ticket:", textwrap.shorten(p.get("summary") or "", 110) if p else "(answered; see reply)")
    print("  why:   ", why)
    if r.get("reply"):
        print("  reply: ", textwrap.fill(r["reply"], 100, subsequent_indent="          "))
        cites = sorted({c for s in r["generation"]["sentences"] for c in s["cite"]})
        print("  cites: ", ", ".join(cites))
    if p.get("articles"):
        print("  sent to a person with articles:", ", ".join(p["articles"]))
