# CloudServe Support

Ticket triage and grounded answering for CloudServe Solutions (FDE capstone).

## Setup

Requires Python 3.11 (macOS: `brew install python@3.11`).

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then put your model provider key in .env
```

The first run downloads the `all-MiniLM-L6-v2` embedding model (~90 MB).

## Run the evaluation

Processes every ticket in the file, unattended, and writes the results, decision log and metrics report:

```bash
python -m evaluation.harness --input data/validation_tickets.json --output evaluation/results/
```

`--input` accepts any file with the same schema (a JSON list of tickets). Output directory contents:

| File | Contents |
|---|---|
| `results.jsonl` | One line per ticket: final action, reply or escalation packet, classification, checks |
| `decisions.db` | SQLite decision log, one row per automated decision |
| `metrics.json`, `metrics.md` | Volume, business, technical, governance and fairness figures |

If the model provider is down, tickets that would have been answered are escalated with context instead;
the run still completes.

## Configuration

Set in `.env` (see `.env.example`): `OPENROUTER_API_KEY`, `MODEL_NAME` and `MODEL_FALLBACKS` (tried in order),
`CONFIDENCE_THRESHOLD` (0.85), `INTENT_MIN_CONFIDENCE` (0.50), `RETRIEVAL_MIN_SCORE` (0.40).
Model responses are cached in `storage/llm_cache/`; delete it to force fresh calls.

## Tests

```bash
python -m pytest tests/ -v
```

## Dependencies

`requirements.in` lists top-level packages; `requirements.txt` is the full pinned lock.
To change a dependency, edit `requirements.in`, reinstall in a fresh venv, then
`pip freeze > requirements.txt`.
