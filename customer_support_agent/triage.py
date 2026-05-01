"""Top-level triage orchestrator: classify → draft → HITL queue.

Single function `triage(messages)` does the whole pipeline:

  for each message:
    1. classify (Claude or heuristic)
    2. record_example for L3 skill library (so 'classify-support-message'
       skill can be distilled from successful classifications)
    3. log_outcome on FAILED/PARTIAL classifications
    4. draft_reply if classification is non-spam
    5. write draft to HITL queue (~/.customer-support-agent/queue/pending/)

Returns a TriageReport summarizing the run for the morning brief.
"""
from __future__ import annotations
import json
import pathlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from solo_founder_os.anthropic_client import AnthropicClient

from .classifier import classify
from .drafter import draft_reply
from .types import Draft, Message


HITL_QUEUE_DIR = (pathlib.Path.home()
                   / ".customer-support-agent" / "queue" / "pending")


@dataclass
class TriageReport:
    """Summary of one triage run."""
    n_total: int = 0
    by_label: dict[str, int] = field(default_factory=dict)
    n_drafts_queued: int = 0
    n_spam_skipped: int = 0
    n_novel_flagged: int = 0
    drafts: list[Draft] = field(default_factory=list)


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "msg"


def _write_to_queue(draft: Draft, *, base: Optional[pathlib.Path] = None) -> pathlib.Path:
    base = base or HITL_QUEUE_DIR
    base.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sender_slug = _slug(draft.sender.split("@")[0])
    label = draft.classification.label
    path = base / f"{today}-{label}-{sender_slug}.md"
    if path.exists():
        for i in range(2, 100):
            cand = base / f"{today}-{label}-{sender_slug}-{i}.md"
            if not cand.exists():
                path = cand
                break
    parts = [
        "---",
        f"sender: {draft.sender}",
        f"subject: {draft.subject}",
        f"label: {label}",
        f"confidence: {draft.classification.confidence:.2f}",
        f"drafted_at: {(draft.drafted_at or datetime.now(timezone.utc)).isoformat()}",
        f"priority: {('high' if label in ('signup_broken', 'forge_stuck', 'billing') else 'med')}",
        "---",
        "",
        f"# Reply draft to {draft.sender}",
        "",
        f"**Classification reasoning:** {draft.classification.reasoning}",
        "",
        "## Reply",
        "",
        draft.body,
        "",
    ]
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def triage(
    messages: list[Message],
    *,
    client: Optional[AnthropicClient] = None,
    queue_dir: Optional[pathlib.Path] = None,
) -> TriageReport:
    """End-to-end triage of a batch of messages.

    `client` is injectable for tests. In production leave None and the
    constituent functions construct their own AnthropicClient pointed at
    the customer-support usage log.

    `queue_dir` overrides the default HITL queue dir (for tests).
    """
    report = TriageReport(n_total=len(messages))

    for msg in messages:
        cls = classify(msg, client=client)
        report.by_label[cls.label] = report.by_label.get(cls.label, 0) + 1

        # L3: record successful classifications for future distillation
        if cls.confidence >= 0.6 and cls.label != "novel":
            try:
                from solo_founder_os import record_example
                record_example(
                    "classify-support-message",
                    inputs={
                        "subject": msg.subject[:200],
                        "body_preview": msg.body[:500],
                        "source": msg.source,
                    },
                    output=json.dumps({
                        "label": cls.label,
                        "confidence": cls.confidence,
                        "reasoning": cls.reasoning,
                    }),
                    note=f"label={cls.label}",
                )
            except Exception:
                pass

        # L1: log failures (low-confidence classifications + novel ones)
        if cls.confidence < 0.5 or cls.label == "novel":
            try:
                from solo_founder_os import log_outcome
                log_outcome(
                    ".customer-support-agent",
                    task="classify",
                    outcome="PARTIAL",
                    signal=(f"low confidence ({cls.confidence:.2f}) "
                            f"or novel: {cls.reasoning[:120]}"),
                )
            except Exception:
                pass

        if cls.label == "spam":
            report.n_spam_skipped += 1
            continue
        if cls.label == "novel":
            report.n_novel_flagged += 1

        d = draft_reply(msg, cls, client=client)
        if d is None:
            continue
        _write_to_queue(d, base=queue_dir)
        report.drafts.append(d)
        report.n_drafts_queued += 1

    return report
