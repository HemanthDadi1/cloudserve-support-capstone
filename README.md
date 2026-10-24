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

## Tests

```bash
python -m pytest tests/ -v
```

## Dependencies

`requirements.in` lists top-level packages; `requirements.txt` is the full pinned lock.
To change a dependency, edit `requirements.in`, reinstall in a fresh venv, then
`pip freeze > requirements.txt`.
