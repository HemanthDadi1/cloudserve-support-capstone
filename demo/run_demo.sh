#!/bin/zsh
# Guided live demo for the video. Press Enter to move to each step. Run from the repo root:
#   ./demo/run_demo.sh
# Talking points for each step are in demo/DEMO.md.
cd "${0:A:h}/.." || exit 1
source .venv/bin/activate || exit 1
rm -f storage/AUTOMATION_OFF

step() { print -P "\n%F{yellow}=== $1%f"; print -P "%F{8}$2%f"; read -r "?(Enter to run) "; }

step "1. Six demo tickets, run unattended" "python -m evaluation.harness --input demo/demo_tickets.json --output demo/out/"
python -m evaluation.harness --input demo/demo_tickets.json --output demo/out/ 2>&1 | grep -E "^\[|Done"

step "2. What happened to each ticket and why" "python demo/show.py demo/out/results.jsonl"
python demo/show.py demo/out/results.jsonl

step "3. The decision log: one row per decision, with its reason and requirement" "sqlite3 demo/out/decisions.db ..."
sqlite3 -list -separator '  |  ' demo/out/decisions.db \
  "select ticket_id, stage, action_taken, substr(reason,1,48), requirement_ids from decisions order by ticket_id, decision_id;"

step "4. Kill switch on: nothing is answered" "touch storage/AUTOMATION_OFF, then run the same six tickets"
touch storage/AUTOMATION_OFF
python -m evaluation.harness --input demo/demo_tickets.json --output demo/out_off/ 2>&1 | grep -E "^\[|Done"
rm -f storage/AUTOMATION_OFF
print -P "%F{green}Kill switch removed.%f"

step "5. The full unattended run: all 80 validation tickets" "python -m evaluation.harness --input data/validation_tickets.json --output evaluation/results/"
[[ -n $DEMO_FRESH ]] && rm -rf storage/llm_cache   # DEMO_FRESH=1 ./demo/run_demo.sh: real model calls
python -m evaluation.harness --input data/validation_tickets.json --output evaluation/results/ 2>&1 | grep -E "^\[|Done" | tail -15

step "6. The report it wrote: volume, then governance" "sed -n on evaluation/results/metrics.md"
sed -n '/^## Volume/,/^## Business/p' evaluation/results/metrics.md | sed '$d'
sed -n '/^## Governance/,/^## Fairness/p' evaluation/results/metrics.md | sed '$d'
print -P "\n%F{green}Demo finished.%f"
