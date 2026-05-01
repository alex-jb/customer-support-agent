"""CLI: `customer-support-agent <subcommand>`.

Subcommands:
    triage --inbox <path>     Read messages from a JSONL file, run pipeline
    classify "<text>"         One-shot: classify a single message
    queue-status              Count + list pending HITL drafts
"""
from __future__ import annotations
import argparse
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

from .classifier import classify
from .triage import HITL_QUEUE_DIR, triage
from .types import Message


def cmd_triage(args) -> int:
    inbox = pathlib.Path(args.inbox).expanduser()
    if not inbox.exists():
        print(f"inbox file not found: {inbox}", file=sys.stderr)
        return 1
    messages: list[Message] = []
    for line in inbox.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        messages.append(Message(
            source=row.get("source", "manual"),
            source_id=row.get("source_id") or row.get("id") or "?",
            sender=row.get("sender", "?"),
            subject=row.get("subject", ""),
            body=row.get("body", ""),
        ))
    if not messages:
        print("(inbox empty)", file=sys.stderr)
        return 0
    report = triage(messages)
    print(f"# Customer support triage — {datetime.now(timezone.utc).isoformat()}")
    print(f"Messages processed: {report.n_total}")
    print(f"By label: {dict(report.by_label)}")
    print(f"Drafts queued: {report.n_drafts_queued}")
    print(f"Spam skipped: {report.n_spam_skipped}")
    print(f"Novel (need human reply): {report.n_novel_flagged}")
    return 0


def cmd_classify(args) -> int:
    msg = Message(
        source="manual", source_id="cli",
        sender=args.sender or "user",
        subject=args.subject or "",
        body=args.text,
    )
    cls = classify(msg)
    print(f"label={cls.label} confidence={cls.confidence:.2f}")
    print(f"reasoning: {cls.reasoning}")
    if cls.keywords_matched:
        print(f"keywords: {', '.join(cls.keywords_matched[:5])}")
    return 0


def cmd_queue_status(args) -> int:
    base = pathlib.Path(args.dir).expanduser() if args.dir else HITL_QUEUE_DIR
    if not base.exists():
        print(f"(no queue at {base})", file=sys.stderr)
        return 0
    files = sorted(base.glob("*.md"))
    if not files:
        print("(queue empty)", file=sys.stderr)
        return 0
    print(f"# Pending drafts ({len(files)})")
    for p in files:
        print(f"  - {p.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if os.getenv("CUSTOMER_SUPPORT_SKIP") == "1":
        return 0

    p = argparse.ArgumentParser(
        prog="customer-support-agent",
        description="Triage user messages: classify → draft → HITL queue.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("triage", help="Run pipeline over a JSONL inbox.")
    t.add_argument("--inbox", required=True,
                    help="JSONL file: one message per line "
                         "(keys: source, source_id, sender, subject, body).")
    t.set_defaults(func=cmd_triage)

    c = sub.add_parser("classify", help="One-shot classify a single message.")
    c.add_argument("text", help="Message body.")
    c.add_argument("--subject", default=None)
    c.add_argument("--sender", default=None)
    c.set_defaults(func=cmd_classify)

    q = sub.add_parser("queue-status", help="List pending HITL drafts.")
    q.add_argument("--dir", default=None,
                    help="Override queue dir (default: "
                         "~/.customer-support-agent/queue/pending/)")
    q.set_defaults(func=cmd_queue_status)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
