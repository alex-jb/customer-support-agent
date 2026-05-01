"""Classify incoming user messages into one of N templates.

Claude path (preferred): structured output with the label set fixed by
schema. Heuristic fallback: keyword regex per label, picks highest-match.

Six default labels (override via classify(templates=...)):
  - signup_broken    auth/login/register failures
  - forge_stuck      core flow stuck (project review/forge incomplete)
  - billing          payment / refund / subscription questions
  - love             positive/encouraging messages, no action needed
  - spam             irrelevant / promotional / scam
  - novel            doesn't match any known template — flag for human

The agent ALWAYS produces a label. The fallback to "novel" is the
escape hatch when Claude is uncertain and heuristics don't match.
"""
from __future__ import annotations
import os
import pathlib
import re
from typing import Optional

from solo_founder_os.anthropic_client import (
    AnthropicClient,
    DEFAULT_HAIKU_MODEL,
)

from .types import Classification, Message


USAGE_LOG_PATH = (pathlib.Path.home()
                  / ".customer-support-agent" / "usage.jsonl")


# Default templates: (label, keyword regex, brief description for the LLM)
DEFAULT_TEMPLATES: list[tuple[str, str, str]] = [
    ("signup_broken",
     r"\b(sign[- ]?up|signup|register|login|sign[- ]?in|verify|verification|"
     r"oauth|password|reset|email|confirm|invite|magic[- ]?link)\b",
     "auth flow problem (signup, login, password reset, OAuth, magic link)"),
    ("forge_stuck",
     r"\b(forge|stuck|spinning|loading forever|review didn'?t|never finished|"
     r"hung|frozen|broken|doesn'?t work)\b",
     "core flow problem (project review/forge stuck, broken page, 5xx)"),
    ("billing",
     r"\b(bill|billing|charge|charged|invoice|refund|cancel|subscribe|"
     r"subscription|payment|stripe|paid|upgrade|downgrade|pro plan|free tier)\b",
     "payment / billing / subscription question"),
    ("love",
     r"\b(love|amazing|great|cool|awesome|nice|congrats|congratulations|"
     r"impressive|beautiful|❤️|🔥|🎉|🚀)\b",
     "positive feedback or congrats; no action required beyond a thank-you"),
    ("spam",
     r"\b(crypto|nft|airdrop|bot|escort|investment opportunity|cheap |"
     r"discount code|promo|click here|free seo|backlink)\b",
     "irrelevant / promotional / scam — should be ignored or filed"),
]


CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
    },
    "required": ["label", "confidence", "reasoning"],
    "additionalProperties": False,
}


def _heuristic(message: Message,
                 templates: list[tuple[str, str, str]]) -> Classification:
    """Keyword-regex fallback. Picks the label with most matches; falls back
    to 'novel' if zero matches anywhere."""
    text = f"{message.subject}\n{message.body}".lower()
    scores: dict[str, list[str]] = {}
    for label, pattern, _desc in templates:
        hits = re.findall(pattern, text, re.IGNORECASE)
        if hits:
            scores[label] = list({str(h).lower() for h in hits})
    if not scores:
        return Classification(label="novel", confidence=0.3,
                                reasoning="no keyword match across any template")
    # Pick label with most distinct matches
    best = max(scores.items(), key=lambda kv: len(kv[1]))
    label, kws = best
    # Confidence scales with match count: 1 hit = 0.4, 2 = 0.55, 3+ = 0.7
    conf = min(0.7, 0.25 + 0.15 * len(kws))
    return Classification(
        label=label,
        confidence=conf,
        reasoning=f"keyword match: {', '.join(kws[:3])}",
        keywords_matched=kws,
    )


def classify(
    message: Message,
    *,
    templates: Optional[list[tuple[str, str, str]]] = None,
    client: Optional[AnthropicClient] = None,
) -> Classification:
    """Classify one message. Returns a Classification with label + confidence.

    Tries Claude (Haiku) with structured output first. On no key / API
    error / unrecognized label, falls back to heuristic regex matching.
    Always returns a Classification — never None.
    """
    templates = templates or DEFAULT_TEMPLATES
    valid_labels = {label for label, _, _ in templates} | {"novel"}

    if client is None:
        client = AnthropicClient(usage_log_path=USAGE_LOG_PATH)

    if not client.configured:
        return _heuristic(message, templates)

    template_lines = "\n".join(
        f"  - {label}: {desc}" for label, _, desc in templates)
    template_lines += "\n  - novel: doesn't match any of the above"

    user = (
        "Classify this user message into ONE label.\n\n"
        f"Available labels:\n{template_lines}\n\n"
        f"Subject: {message.subject[:200]}\n"
        f"From: {message.sender[:120]}\n"
        f"Body:\n{message.body[:2000]}\n\n"
        "Output JSON. label MUST be exactly one of the labels above.\n"
        "confidence is 0.0–1.0. reasoning is one short sentence."
    )

    obj, err = client.messages_create_json(
        schema=CLASSIFY_SCHEMA,
        model=DEFAULT_HAIKU_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": user}],
    )
    if err is not None or obj is None:
        return _heuristic(message, templates)

    label = (obj.get("label") or "").strip().lower()
    if label not in valid_labels:
        # Claude tried to invent a label — fall back
        return _heuristic(message, templates)

    confidence = float(obj.get("confidence") or 0.5)
    confidence = max(0.0, min(1.0, confidence))
    reasoning = (obj.get("reasoning") or "").strip()[:300]

    return Classification(
        label=label, confidence=confidence, reasoning=reasoning,
    )


def n_known_labels(templates: Optional[list] = None) -> int:
    """How many labels in the active template set, including 'novel'."""
    templates = templates or DEFAULT_TEMPLATES
    return len(templates) + 1


# Suppress unused-import warning while keeping the export available
_ = os
