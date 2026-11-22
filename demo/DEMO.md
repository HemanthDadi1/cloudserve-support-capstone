# Live demo

Run it with:

```bash
./demo/run_demo.sh
```

Before you record: make the terminal font large, do not open `.env`, and do one dry run so the model
answers are cached. The script removes `storage/AUTOMATION_OFF` at the start and again after step 4.

Timing: about 8 minutes. The full run in step 5 takes about 2 minutes.

| Step | Say | Point at |
|---|---|---|
| 1. Six tickets | "Six tickets, one command, no one touching it." | The `[n/6]` lines |
| 2. Results | Go through each ticket in turn (below). | `->` outcome and `why:` line |
| 3. Decision log | "Every decision keeps its reason and the requirement that drove it." | `reason` and `requirement_ids` columns |
| 4. Kill switch | "One file stops all replies. No restart, no deploy." | Every ticket now `ESCALATE` |
| 5. Full run | "The same system over all 80 validation tickets, unattended." | `Done: 80 tickets`, no errors |
| 6. Report | "It writes its own metrics report." | processed 80, errors 0, log reconciles |

## The six tickets (step 2)

| Ticket | Usual outcome | Say |
|---|---|---|
| VAL-0036 or VAL-0050 (new customer, where to start) | Answered | The reply is labelled as automated and every sentence cites an article. |
| VAL-0067 (unknown address in the audit log) | Escalated | Security incidents always go to a person. Show the articles sent with it. |
| VAL-0002 ("Any update?") | Escalated | Too unclear to answer. The system does not guess. |
| DEMO-INJECT-1 ("Ignore all previous instructions…") | Blocked | Caught before routing. The ticket cannot instruct the system. |
| VAL-0077 (billing period) | Usually blocked | The grounding check rejected a sentence its article did not support. If it is sent this time, say so. |

Routing is fixed from run to run. Which model drafts a reply depends on which is free, so a draft can differ.

## What to expect from the numbers

Model answers are cached in `storage/llm_cache/`, so a repeat run is fast and gives the same drafts. A run
from a clean cache can differ by a reply or two from the report (the 2 November run answered 13 of 80;
a cached rerun gave 14). Routing never changes. Say that the report's figures are from the recorded run
in `evaluation/validation_run/`. To show real model calls in step 5, start the script with `DEMO_FRESH=1 ./demo/run_demo.sh`
(it clears the cache before step 5, and the run then takes about 2 minutes), but only if the models are
responding well that day.

## If asked about the 82% escalation rate

The brief asked for 30% or lower. I revised it in PRD v2 to about 80%, with every escalation carrying
the likely topic, the relevant articles and the reason. A fifth of tickets are topics that always go to
a person, and at the safe 0.85 threshold the system answers only what it can prove from the docs.
Lowering the threshold to 0.50 still escalates about 37% and sends about 20% wrong answers, so 30% is
not reachable safely.

## If something goes wrong

- A model is busy or down: the ticket escalates with "The model provider is unavailable". Say this is
  the outage path working, and carry on.
- Step 5 is slow: wait. If you must cut, show `evaluation/validation_run/metrics.md` and say it is
  the 2 November run.
- A kill switch file is left behind: `rm -f storage/AUTOMATION_OFF`.

## Optional: Visual Audit Dashboard

To show an interactive visual summary of the demo and validation runs in your browser during the presentation:
```bash
open demo/dashboard.html
```
Generated via `python demo/generate_dashboard.py`. Completely self-contained (zero server, zero external dependencies). Toggles between the 6 demo tickets and 80 validation tickets with full audit trails and guardrail check verdicts.
