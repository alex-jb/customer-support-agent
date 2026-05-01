"""MCP server — let Claude Desktop / Cursor / Zed triage user messages.

Tools:
  - classify_message(text, subject, sender)  → label + confidence
  - draft_support_reply(text, subject, sender, label?) → markdown reply

Install: pip install 'customer-support-agent[mcp]'
"""
from __future__ import annotations
import os
import sys

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    print("customer-support-mcp requires the `mcp` package. "
          "Install with: pip install 'customer-support-agent[mcp]'",
          file=sys.stderr)
    raise SystemExit(1) from e

from .classifier import classify
from .drafter import draft_reply
from .types import Classification, Message


mcp = FastMCP("customer-support")


@mcp.tool()
def classify_message(text: str, subject: str = "",
                       sender: str = "user") -> str:
    """Classify a user message into one of: signup_broken / forge_stuck /
    billing / love / spam / novel. Returns markdown summary."""
    msg = Message(source="mcp", source_id="adhoc",
                   sender=sender, subject=subject, body=text)
    cls = classify(msg)
    out = [
        f"**Label:** {cls.label}",
        f"**Confidence:** {cls.confidence:.2f}",
        f"**Reasoning:** {cls.reasoning}",
    ]
    if cls.keywords_matched:
        out.append(f"**Keywords:** {', '.join(cls.keywords_matched[:5])}")
    return "\n".join(out)


@mcp.tool()
def draft_support_reply(text: str, subject: str = "",
                          sender: str = "user",
                          label: str = "") -> str:
    """Draft a support reply for a message. If `label` is provided, skip
    classification and use it. Otherwise classify first."""
    msg = Message(source="mcp", source_id="adhoc",
                   sender=sender, subject=subject, body=text)
    if label:
        cls = Classification(label=label.strip().lower(), confidence=1.0,
                              reasoning="user-specified label")
    else:
        cls = classify(msg)
    draft = draft_reply(msg, cls)
    if draft is None:
        return f"_(skipped: classified as {cls.label})_"
    return (
        f"**Subject:** {draft.subject}\n"
        f"**Label:** {cls.label} ({cls.confidence:.2f})\n\n"
        f"{draft.body}"
    )


def main() -> None:
    if os.getenv("CUSTOMER_SUPPORT_SKIP") == "1":
        return
    mcp.run()


if __name__ == "__main__":
    main()
