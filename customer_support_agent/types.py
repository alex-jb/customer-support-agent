"""Core types — pure dataclasses, no LLM dependency."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# Single source of truth for classification labels. Add new ones here;
# every other module reads from this list.
ClassLabel = str  # "signup_broken" | "forge_stuck" | "billing" | "love" | "spam" | "novel"


@dataclass
class Message:
    """One incoming user message regardless of source (email / PH / X / DM)."""
    source: str  # "email" | "producthunt" | "twitter" | "discord" | "manual"
    source_id: str  # stable id within the source, for dedup
    sender: str  # email or handle
    subject: str = ""
    body: str = ""
    received_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.received_at is None:
            self.received_at = datetime.now(timezone.utc)


@dataclass
class Classification:
    """The classifier's verdict for one message."""
    label: ClassLabel
    confidence: float  # 0..1 — Haiku's self-reported confidence
    reasoning: str  # one-liner why this label
    keywords_matched: list[str] = field(default_factory=list)


@dataclass
class Draft:
    """An auto-drafted reply ready for HITL review."""
    message_id: str  # Message.source_id
    sender: str
    subject: str  # "Re: <original>"
    body: str
    classification: Classification
    drafted_at: Optional[datetime] = None
    raw_prompt: str = ""
    raw_response: str = ""

    def __post_init__(self):
        if self.drafted_at is None:
            self.drafted_at = datetime.now(timezone.utc)
