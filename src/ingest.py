"""Ingest: normalise tickets from all four channels into one Ticket (acceptance criterion A2).

Channels differ only in shape (chat has no subject), so one normaliser handles all of them.
Malformed input never raises: missing fields become empty strings, the raw record is kept.
"""
import re
import unicodedata

from pydantic import BaseModel

CHANNELS = {"email", "chat", "docs_comment", "forum"}


class Ticket(BaseModel):
    ticket_id: str
    channel: str  # one of CHANNELS, or "unknown"
    subject: str
    body: str
    text: str  # subject + body, cleaned; what downstream components read
    received_at: str
    customer_id: str
    customer_name: str
    customer_tier: str
    customer_region: str
    language_fluency: str
    raw: dict  # original record, preserved unchanged


def clean(value) -> str:
    s = unicodedata.normalize("NFKC", "" if value is None else str(value))
    s = "".join(c for c in s if c in "\n\t" or unicodedata.category(c)[0] != "C")
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", s)).strip()


def normalize(raw, fallback_id: str = "UNKNOWN") -> Ticket:
    raw = raw if isinstance(raw, dict) else {"body": raw}
    get = lambda k: clean(raw.get(k))  # noqa: E731
    channel = get("channel").lower()
    subject, body = get("subject"), get("body")
    return Ticket(
        ticket_id=get("ticket_id") or fallback_id,
        channel=channel if channel in CHANNELS else "unknown",
        subject=subject,
        body=body,
        text="\n".join(p for p in (subject, body) if p),
        received_at=get("received_at"),
        customer_id=get("customer_id"),
        customer_name=get("customer_name"),
        customer_tier=get("customer_tier"),
        customer_region=get("customer_region"),
        language_fluency=get("language_fluency"),
        raw=raw,
    )
