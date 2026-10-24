import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def test_datasets_load():
    assert len(json.loads((DATA / "documentation.json").read_text())) == 29
    assert len(json.loads((DATA / "development_tickets.json").read_text())) == 500
