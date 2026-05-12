"""Plan-first pattern tests.

The plan-first invariant is the architectural guard against drift in
long-running support workflows. These tests are the wall.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from customer_support_agent.planner import (
    PlanRequired,
    SupportPlan,
    read_plan,
    require_plan_or_raise,
    write_plan,
)


def _make_plan(ticket_id: str = "t-001") -> SupportPlan:
    return SupportPlan(
        ticket_id=ticket_id,
        intent="BILLING",
        severity="P2_medium",
        response_needed=True,
        one_line_summary="User cannot find their last invoice PDF.",
        resolution_steps=[
            "Acknowledge issue + apologize for friction",
            "Link to billing.example.com/invoices",
            "If 24h no response, escalate to founder",
        ],
        escalation_threshold="user replies 'still broken' within 4 hours OR mentions chargeback",
        allowed_actions=["link to billing page", "regenerate invoice PDF"],
        forbidden_actions=["promise refund (out of scope for tier-1)", "schedule call"],
        estimated_cost_usd=0.003,
    )


def test_plan_roundtrip(tmp_path: Path):
    p = _make_plan()
    path = write_plan(p, root=tmp_path)
    assert path.exists()
    loaded = read_plan(p.ticket_id, root=tmp_path)
    assert loaded is not None
    assert loaded.intent == "BILLING"
    assert loaded.severity == "P2_medium"
    assert "regenerate invoice PDF" in loaded.allowed_actions


def test_plan_json_is_human_readable(tmp_path: Path):
    p = _make_plan()
    path = write_plan(p, root=tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    # plain dict, no nested objects → human can read + edit
    assert isinstance(raw, dict)
    assert raw["ticket_id"] == "t-001"
    assert raw["intent"] == "BILLING"


def test_require_plan_raises_when_missing(tmp_path: Path):
    with pytest.raises(PlanRequired, match="No plan found"):
        require_plan_or_raise("missing-ticket-id", root=tmp_path)


def test_require_plan_returns_when_present(tmp_path: Path):
    p = _make_plan("t-002")
    write_plan(p, root=tmp_path)
    loaded = require_plan_or_raise("t-002", root=tmp_path)
    assert loaded.ticket_id == "t-002"


def test_plan_unicode_safe(tmp_path: Path):
    """Plans with Chinese text must round-trip without corruption."""
    p = SupportPlan(
        ticket_id="zh-1",
        intent="HOW_TO",
        severity="P3_low",
        response_needed=True,
        one_line_summary="用户问怎么导出 CSV — 一句话解释 + 链接",
        resolution_steps=["指向 帮助中心 → 导出 CSV"],
    )
    write_plan(p, root=tmp_path)
    loaded = read_plan("zh-1", root=tmp_path)
    assert loaded is not None
    assert "导出 CSV" in loaded.one_line_summary
    assert "帮助中心" in loaded.resolution_steps[0]


def test_forbidden_actions_are_explicit(tmp_path: Path):
    """The whole point of the plan-first pattern: drafter can't improvise
    actions outside `allowed_actions`. forbidden_actions must be readable
    in the plan file so a human reviewer can audit."""
    p = _make_plan()
    write_plan(p, root=tmp_path)
    loaded = read_plan("t-001", root=tmp_path)
    assert "promise refund (out of scope for tier-1)" in loaded.forbidden_actions
