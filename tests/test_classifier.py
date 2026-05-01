"""Tests for the classifier — heuristic + Claude path."""
from __future__ import annotations
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from customer_support_agent.classifier import (
    DEFAULT_TEMPLATES,
    _heuristic,
    classify,
    n_known_labels,
)
from customer_support_agent.types import Message


def _msg(body: str, subject: str = "") -> Message:
    return Message(source="manual", source_id="t1", sender="u@x",
                    subject=subject, body=body)


def _fake_client(*, configured: bool = True,
                  label: str | None = "signup_broken",
                  confidence: float = 0.85,
                  reasoning: str = "user mentions login error",
                  err: str | None = None):
    c = MagicMock()
    c.configured = configured
    if err:
        c.messages_create_json.return_value = (None, err)
    else:
        c.messages_create_json.return_value = ({
            "label": label, "confidence": confidence,
            "reasoning": reasoning,
        }, None)
    return c


# ── Heuristic tests ────────────────────────────────────────


def test_heuristic_signup_broken():
    cls = _heuristic(_msg("My signup link doesn't work — never got the verification email"),
                       DEFAULT_TEMPLATES)
    assert cls.label == "signup_broken"
    assert cls.confidence > 0.4


def test_heuristic_forge_stuck():
    cls = _heuristic(_msg("My project has been spinning forever"),
                       DEFAULT_TEMPLATES)
    assert cls.label == "forge_stuck"


def test_heuristic_billing():
    cls = _heuristic(_msg("Need a refund for the Pro plan"),
                       DEFAULT_TEMPLATES)
    assert cls.label == "billing"


def test_heuristic_love():
    cls = _heuristic(_msg("This is amazing! 🚀 Congrats on the launch"),
                       DEFAULT_TEMPLATES)
    assert cls.label == "love"


def test_heuristic_spam():
    cls = _heuristic(_msg("Cheap SEO backlinks click here for nft airdrop"),
                       DEFAULT_TEMPLATES)
    assert cls.label == "spam"


def test_heuristic_novel_no_match():
    cls = _heuristic(_msg("I want to discuss your roadmap for Q4"),
                       DEFAULT_TEMPLATES)
    assert cls.label == "novel"
    assert cls.confidence < 0.5


# ── Claude path ────────────────────────────────────────────


def test_classify_unconfigured_falls_back_to_heuristic():
    fake = _fake_client(configured=False)
    cls = classify(_msg("My login is broken"), client=fake)
    # Heuristic should pick signup_broken
    assert cls.label == "signup_broken"
    assert fake.messages_create_json.call_count == 0


def test_classify_uses_claude_label():
    fake = _fake_client(label="forge_stuck", confidence=0.92,
                          reasoning="user reports forge timeout")
    cls = classify(_msg("ambiguous text"), client=fake)
    assert cls.label == "forge_stuck"
    assert cls.confidence == 0.92


def test_classify_invalid_label_falls_back():
    """If Claude returns a label not in our set, fall back to heuristic."""
    fake = _fake_client(label="hallucinated_label")
    cls = classify(_msg("My signup is broken"), client=fake)
    # Heuristic match → signup_broken (not hallucinated)
    assert cls.label == "signup_broken"


def test_classify_anthropic_error_falls_back():
    fake = _fake_client(err="rate limit")
    cls = classify(_msg("payment refund please"), client=fake)
    assert cls.label == "billing"


def test_classify_clamps_confidence():
    """Confidence outside [0,1] gets clamped."""
    fake = _fake_client(confidence=2.0)
    cls = classify(_msg("x"), client=fake)
    assert cls.confidence <= 1.0
    fake = _fake_client(confidence=-0.5)
    cls = classify(_msg("x"), client=fake)
    assert cls.confidence >= 0.0


# ── Sanity ────────────────────────────────────────────────


def test_n_known_labels():
    assert n_known_labels() == len(DEFAULT_TEMPLATES) + 1  # +novel


def test_default_templates_cover_six_labels():
    labels = [label for label, _, _ in DEFAULT_TEMPLATES]
    expected = {"signup_broken", "forge_stuck", "billing", "love", "spam"}
    assert set(labels) == expected
