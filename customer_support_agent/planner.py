"""Plan-first pattern — borrowed from langchain-ai/deepagents (22.7k⭐, +50%/30d).

The deepagents architectural primitive: BEFORE the agent takes any
classify/triage/draft action, it MUST emit a structured plan covering
the entire ticket lifecycle. Downstream steps reference the plan
rather than re-reasoning the ticket from scratch each call.

Benefits we get from this pattern:

1. **Auditability** — every support ticket has a plan.json next to the
   draft.md. Reviewer can read the plan and judge whether downstream
   classification / draft matched the plan's intent.
2. **Re-runnable** — if drafter fails, we re-run drafter with the same
   plan instead of restarting from triage. Saves ~$0.003/restart.
3. **Anti-drift** — Sonnet drafter can't "improvise" a refund offer
   that wasn't in the plan; the plan caps the action space.
4. **Cross-agent skill transfer** — same plan format works for
   payments-agent (overdue-invoice ladder) so SFOS L3 skill library
   can extract reusable plan templates.

This module ONLY produces the plan. classifier.py / triage.py / drafter.py
read the plan as input. To enable hard enforcement, downstream steps
should `require_plan_or_raise(ticket_id)`.

Pattern provenance: langchain-ai/deepagents (Apache-2.0, 2026-05). We
adopt the plan-file primitive; we do NOT pull deepagents as a runtime
dependency (it would couple SFOS to LangGraph version churn).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional


Intent = Literal[
    "BUG_REPORT",           # actual product bug
    "FEATURE_REQUEST",      # user wants something we don't have
    "HOW_TO",               # confused about existing feature
    "BILLING",              # payment / invoice / refund
    "ACCOUNT_ACCESS",       # login / reset / 2FA
    "COMPLAINT",            # angry, no specific ask
    "SPAM",                 # bot / off-topic
    "OTHER",
]

Severity = Literal["P0_critical", "P1_high", "P2_medium", "P3_low"]


@dataclass
class SupportPlan:
    """Structured plan for one support ticket. Persisted as plan.json.

    All downstream steps (classifier, triage, drafter) read this file
    as the SOURCE OF TRUTH for what the response should accomplish.
    """
    ticket_id: str
    intent: Intent
    severity: Severity
    response_needed: bool             # False for spam / acknowledgements
    one_line_summary: str             # what the user actually wants in <140 chars
    resolution_steps: list[str] = field(default_factory=list)
    escalation_threshold: str = ""    # when to escalate to human (free text)
    allowed_actions: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    estimated_cost_usd: float = 0.0
    plan_created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    plan_version: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


def _default_root() -> Path:
    return Path(
        os.environ.get("CSA_HOME", Path.home() / ".customer_support_agent")
    ) / "plans"


def write_plan(plan: SupportPlan, root: Optional[Path] = None) -> Path:
    """Write the plan to disk. Returns the path.

    File location: ~/.customer_support_agent/plans/<ticket_id>.json
    """
    root = root or _default_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{plan.ticket_id}.json"
    path.write_text(
        json.dumps(plan.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def read_plan(ticket_id: str, root: Optional[Path] = None) -> Optional[SupportPlan]:
    """Read a plan back from disk. Returns None if no plan exists."""
    root = root or _default_root()
    path = root / f"{ticket_id}.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return SupportPlan(**raw)


class PlanRequired(RuntimeError):
    """Raised when a downstream step is invoked before write_plan(). The
    plan-first invariant: classifier / triage / drafter all REFUSE TO RUN
    without a plan file present. This is enforced at the code layer, not
    by convention.
    """


def require_plan_or_raise(ticket_id: str, root: Optional[Path] = None) -> SupportPlan:
    """Defensive: downstream steps call this before doing work. If the
    plan doesn't exist, hard-fail rather than silently proceeding without
    a plan to constrain action space.
    """
    plan = read_plan(ticket_id, root=root)
    if plan is None:
        raise PlanRequired(
            f"No plan found for ticket {ticket_id!r}. The plan-first "
            f"invariant requires calling write_plan() before any "
            f"classifier/triage/drafter step. Run: "
            f"customer-support-agent plan --ticket-id {ticket_id}"
        )
    return plan
