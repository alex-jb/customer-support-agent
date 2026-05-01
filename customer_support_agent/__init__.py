"""customer-support-agent — triage incoming user issues for solo founders.

Solo Founder OS agent #9 (the missing 5th layer of the canonical
one-person-company stack: customer support).

When PH-day or post-launch produces a flood of user inquiries (email,
Product Hunt comments, Discord messages, X mentions), this agent:

  1. Reads incoming messages from configured sources (manual paste,
     Gmail IMAP, file dump)
  2. Classifies each into one of N templates (signup-broken /
     forge-stuck / billing / love / spam / novel) via Claude
  3. Auto-drafts a reply for known templates
  4. Routes drafts through the HITL queue — Alex reviews + sends

The novel-issue bucket lands in the morning brief so Alex sees the
real customer-discovery signals, not the routine ones.
"""
__version__ = "0.1.0"

from .types import Message, Classification, Draft, ClassLabel
from .classifier import classify, DEFAULT_TEMPLATES
from .drafter import draft_reply
from .triage import triage

__all__ = [
    "Message", "Classification", "Draft", "ClassLabel",
    "classify", "DEFAULT_TEMPLATES",
    "draft_reply",
    "triage",
]
