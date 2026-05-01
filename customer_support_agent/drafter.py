"""Draft replies for classified messages.

Per-label policy:
  - signup_broken / forge_stuck — auto-draft empathetic reply with
    troubleshooting steps + an "I'll investigate now" promise. ALWAYS HITL.
  - billing — auto-draft acknowledgment + "I'll respond within 24h."
    ALWAYS HITL.
  - love — auto-draft a 1-line thank-you. Optional auto-send (still
    defaults to HITL because the founder cares about tone).
  - spam — skip; no draft.
  - novel — return a placeholder + flag for human writing from scratch.

All drafts go through HITL. Default to "draft, don't send."
"""
from __future__ import annotations
import pathlib
from typing import Optional

from solo_founder_os.anthropic_client import (
    AnthropicClient,
    DEFAULT_HAIKU_MODEL,
)

from .types import Classification, Draft, Message


USAGE_LOG_PATH = (pathlib.Path.home()
                  / ".customer-support-agent" / "usage.jsonl")


# Per-label drafter system prompts.
PROMPTS = {
    "signup_broken": (
        "You are a solo founder writing a quick reply to a user who hit a "
        "signup/login problem. Tone: empathetic, specific, action-oriented.\n"
        "Rules:\n"
        "  - Acknowledge what they reported (don't restate it back word-for-word)\n"
        "  - Offer 2-3 specific troubleshooting steps relevant to the problem\n"
        "  - Promise to investigate now if steps don't help\n"
        "  - End with: 'I'll follow up here within a few hours either way.'\n"
        "  - 80-130 words. No formal sign-off, no marketing.\n"
        "  - First-person 'I', no 'we' or 'our team'."
    ),
    "forge_stuck": (
        "You are a solo founder writing to a user whose project review "
        "got stuck in the forge. Tone: 'this is on me, fixing now'.\n"
        "Rules:\n"
        "  - Acknowledge specifically what they hit\n"
        "  - Tell them you're checking the queue right now\n"
        "  - Offer to manually re-trigger their forge if they reply with the project URL\n"
        "  - 60-100 words. No marketing.\n"
        "  - First-person 'I'."
    ),
    "billing": (
        "You are a solo founder responding to a billing / payment question.\n"
        "Rules:\n"
        "  - Acknowledge the request explicitly\n"
        "  - Promise to respond within 24h with the resolution\n"
        "  - Don't commit to a specific outcome yet (refund, upgrade, etc) — "
        "the founder will handle it personally\n"
        "  - 60-90 words. Polite but not flowery."
    ),
    "love": (
        "Write a 1-2 sentence thank-you to a user who said something kind. "
        "Make it specific to whatever they mentioned. Avoid generic 'thanks "
        "so much'. No emoji unless theirs included one. Under 30 words."
    ),
    "novel": (
        "This message doesn't fit a template. Draft a brief acknowledgment "
        "(2 sentences max) saying 'I want to think on this and get back to "
        "you'. The founder will write the substantive response themselves."
    ),
}


def draft_reply(
    message: Message,
    classification: Classification,
    *,
    client: Optional[AnthropicClient] = None,
) -> Optional[Draft]:
    """Produce a Draft for the message based on its classification.

    Returns None for spam (no reply needed) or if Claude is unavailable
    AND the label requires a real LLM draft (we don't keyword-template
    replies — too risky in tone).
    """
    label = classification.label
    if label == "spam":
        return None
    if label not in PROMPTS:
        # Unknown label — treat as novel
        label = "novel"

    if client is None:
        client = AnthropicClient(usage_log_path=USAGE_LOG_PATH)
    if not client.configured:
        # No LLM key → emit a placeholder draft so the message still
        # surfaces in the HITL queue with the classification.
        body = (
            f"[no ANTHROPIC_API_KEY — please write reply manually]\n\n"
            f"Classification: {classification.label} "
            f"(confidence {classification.confidence:.2f})\n"
            f"Reasoning: {classification.reasoning}\n\n"
            f"Original:\n> {message.body[:300]}"
        )
        return Draft(
            message_id=message.source_id, sender=message.sender,
            subject=f"Re: {message.subject}" if message.subject else "Re:",
            body=body, classification=classification,
            raw_response="(no API key)",
        )

    system = PROMPTS[label]
    user = (
        f"From: {message.sender}\n"
        f"Subject: {message.subject}\n"
        f"Body:\n{message.body[:2000]}\n\n"
        f"Classification: {label} ({classification.reasoning})"
    )
    resp, err = client.messages_create(
        model=DEFAULT_HAIKU_MODEL,
        max_tokens=400,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    if err is not None or resp is None:
        # Emit placeholder so HITL queue still shows the message
        body = (
            f"[LLM error: {err}]\n\nPlease draft reply manually.\n\n"
            f"Original:\n> {message.body[:300]}"
        )
        return Draft(
            message_id=message.source_id, sender=message.sender,
            subject=f"Re: {message.subject}" if message.subject else "Re:",
            body=body, classification=classification,
            raw_response=f"(error: {err})",
        )
    body = AnthropicClient.extract_text(resp).strip() or "(empty)"
    return Draft(
        message_id=message.source_id,
        sender=message.sender,
        subject=f"Re: {message.subject}" if message.subject else "Re:",
        body=body,
        classification=classification,
        raw_prompt=user,
        raw_response=str(resp)[:500],
    )
