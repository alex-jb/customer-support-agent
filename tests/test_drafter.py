"""Tests for the drafter."""
from __future__ import annotations
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from customer_support_agent.drafter import draft_reply
from customer_support_agent.types import Classification, Message


def _msg() -> Message:
    return Message(source="manual", source_id="m1", sender="alice@x.com",
                    subject="Help with signup", body="The verification "
                    "email never arrived even after waiting 30min.")


def _cls(label: str = "signup_broken", confidence: float = 0.9):
    return Classification(label=label, confidence=confidence,
                            reasoning="signup keyword match")


def _fake_client(*, configured: bool = True, text: str = "I'll investigate now",
                  err: str | None = None):
    c = MagicMock()
    c.configured = configured

    def _create(**kwargs):
        if err:
            return (None, err)
        block = MagicMock()
        block.type = "text"
        block.text = text
        resp = MagicMock()
        resp.content = [block]
        return (resp, None)

    c.messages_create.side_effect = _create
    return c


def test_draft_spam_returns_none():
    """Spam shouldn't get a draft."""
    out = draft_reply(_msg(), _cls(label="spam"),
                       client=_fake_client())
    assert out is None


def test_draft_signup_broken_uses_claude():
    fake = _fake_client(text="Sorry to hear about that. Try X, then Y...")
    draft = draft_reply(_msg(), _cls(label="signup_broken"), client=fake)
    assert draft is not None
    assert "Try X" in draft.body
    assert draft.subject.startswith("Re:")


def test_draft_unconfigured_emits_placeholder():
    """No API key → placeholder draft (still queued for human)."""
    fake = _fake_client(configured=False)
    draft = draft_reply(_msg(), _cls(), client=fake)
    assert draft is not None
    assert "no ANTHROPIC_API_KEY" in draft.body
    assert "manually" in draft.body


def test_draft_anthropic_error_emits_placeholder():
    """LLM error → placeholder draft."""
    fake = _fake_client(err="rate limit")
    draft = draft_reply(_msg(), _cls(), client=fake)
    assert draft is not None
    assert "LLM error" in draft.body


def test_draft_unknown_label_treated_as_novel():
    fake = _fake_client(text="I want to think on this and get back.")
    draft = draft_reply(_msg(), _cls(label="totally_invented"), client=fake)
    assert draft is not None
    # Treated as novel, with appropriate body length
    assert "think on this" in draft.body or "get back" in draft.body


def test_draft_carries_classification():
    fake = _fake_client(text="reply")
    cls = _cls(label="forge_stuck", confidence=0.77)
    draft = draft_reply(_msg(), cls, client=fake)
    assert draft.classification.label == "forge_stuck"
    assert draft.classification.confidence == 0.77
