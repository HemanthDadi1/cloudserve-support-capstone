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

## Kill switch

Stops all automated replies immediately, with no restart or deployment:

```bash
touch storage/AUTOMATION_OFF
```

While that file exists, every ticket is escalated to a person with its context, including any ticket already
being drafted (checked again just before sending). Delete the file to resume. Every decision taken while it is
on is logged with requirement `GOV-KILL-SWITCH`. Set `KILL_SWITCH_PATH` to use a different file.

## Configuration

Set in `.env` (see `.env.example`): `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `MODEL_NAME` and `MODEL_FALLBACKS`
(tried in order; `groq:` models go to Groq, the rest to OpenRouter),
`CONFIDENCE_THRESHOLD` (0.85), `INTENT_MIN_CONFIDENCE` (0.50), `RETRIEVAL_MIN_SCORE` (0.40).
Model responses are cached in `storage/llm_cache/`; delete it to force fresh calls.

## Tests

```bash
python -m pytest tests/ -v
```

## Repository layout

| Path | Contents |
|---|---|
| `src/` | The pipeline: ingest, retrieve, classify, route, generate, validate, decision log, model client |
| `prompts/` | Live prompts (PR-01 answer, PR-02 grounding, PR-03 spec review); `history/` keeps earlier and rejected versions |
| `tests/` | Unit and end-to-end tests; no API keys needed |
| `evaluation/` | Harness, metrics, fairness audit and experiment scripts; `validation_run/` is the recorded validation run |
| `discovery/` | Evidence tables built from the development tickets |
| `docs/` | Architecture notes and the ticket-flow diagram (`docs/architecture.md`) |
| `demo/` | Six tickets for the video demonstration; `python demo/show.py <results.jsonl>` prints a run readably |
| `data/` | Development, validation and documentation files from the capstone pack |

## Attribution and AI tool use

The code, tests and analysis scripts were written with an AI coding assistant (Claude Code) under the
author's direction: the author chose what to build, which experiments to run, and which results to adopt or
reject, and reviewed the results. No third-party code was copied beyond the libraries in `requirements.txt`.
The embedding model is `sentence-transformers/all-MiniLM-L6-v2`; drafts and grounding checks use free-tier
models on Groq and OpenRouter (listed in `.env.example`).

## Dependencies

`requirements.in` lists top-level packages; `requirements.txt` is the full pinned lock.
To change a dependency, edit `requirements.in`, reinstall in a fresh venv, then
`pip freeze > requirements.txt`.
