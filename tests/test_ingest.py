import json

import pytest

from src.ingest import normalize
from tests.test_setup import DATA

TICKETS = json.loads((DATA / "development_tickets.json").read_text())


@pytest.mark.parametrize("channel", ["email", "chat", "docs_comment", "forum"])
def test_each_channel_normalises(channel):
    raw = next(t for t in TICKETS if t["channel"] == channel)
    t = normalize(raw)
    assert t.channel == channel
    assert t.body and t.body in t.text
    assert t.raw == raw


def test_chat_has_no_subject_line():
    t = normalize(next(t for t in TICKETS if t["channel"] == "chat"))
    assert t.subject == "" and t.text == t.body


@pytest.mark.parametrize("raw", [{}, None, "just a string", 42, {"body": None, "channel": None}])
def test_malformed_input_does_not_raise(raw):
    t = normalize(raw, fallback_id="ROW-7")
    assert t.ticket_id == "ROW-7" and t.channel == "unknown"


def test_unusual_characters_are_cleaned():
    t = normalize({"channel": " Email ", "body": "café\x00​  ok\n\n\n\nbye", "subject": "ﬁx"})
    assert t.channel == "email"
    assert t.text == "fix\ncafé ok\n\nbye"
