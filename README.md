# CloudServe Support

[![CI](https://github.com/HemanthDadi1/cloudserve-support-capstone/actions/workflows/ci.yml/badge.svg)](https://github.com/HemanthDadi1/cloudserve-support-capstone/actions/workflows/ci.yml)

Ticket triage and grounded answering for CloudServe Solutions (FDE capstone).

## Setup

Requires Python 3.11 (macOS: `brew install python@3.11`).

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then edit `.env` and replace `your_key_here` with real keys (both are free):

| Variable | Where to get it | Used for |
|---|---|---|
| `GROQ_API_KEY` | console.groq.com | Primary models (fast; 1,000 requests a day per model) |
| `OPENROUTER_API_KEY` | openrouter.ai | Fallback models (50 free requests a day per account) |

With one key the system uses that provider only. With no valid key it still runs: every ticket that
would have been answered is escalated to a person with context, and the run completes.

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
the run still completes. The 80 validation tickets take about 2 minutes on a laptop.

## Configuration

Set in `.env` (see `.env.example`): `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `MODEL_NAME` and `MODEL_FALLBACKS`
(tried in order; `groq:` models go to Groq, the rest to OpenRouter),
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
