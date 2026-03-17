"""
langgraph_orchestrator/nodes.py
================================
All node functions and router functions for the LangGraph StateGraph.

Node contract (LangGraph spec):
  - Input:  full LoanState dict
  - Output: partial dict containing ONLY the keys this node updates
  - LangGraph merges partial outputs into running state automatically
  - Async nodes (run_agents_node) are handled natively by LangGraph

Execution flow:
    validate_input
        │ VALID → run_agents  │ INVALID → END
    run_agents          ← asyncio.gather: all 5 agents in parallel
        │
    hard_stop_check
        │ REJECT → format_response  │ CONTINUE → score_and_decide
    score_and_decide
        │ APPROVE → format_response
        │ REFER   → human_review → format_response
        │ REJECT  → format_response
    format_response → END
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import List

from core.models import (
    AgentResult, AgentStatus, CustomerApplication,
    Decision, LoanDecision,
)
from core.decision_engine import DecisionEngine
from agents.document_verification_agent import DocumentVerificationAgent
from agents.credit_score_agent import CreditScoreAgent
from agents.income_assessment_agent import IncomeAssessmentAgent
from agents.risk_assessment_agent import RiskAssessmentAgent
from agents.compliance_agent import ComplianceAgent
from agents.base import BaseAgent
from config.settings import settings

_engine = DecisionEngine()

HARD_STOP_FLAGS = frozenset({
    "BLACKLIST_HIT", "SANCTIONS_HIT", "RBI_DEFAULTER",
    "PAN_INVALID", "DTI_CRITICAL", "FRAUD_RISK_CRITICAL",
})


# ─────────────────────────────────────────────────────────────────────────────
# NODE 1 — validate_input
# ─────────────────────────────────────────────────────────────────────────────

def validate_input(state: dict) -> dict:
    """
    Validate the CustomerApplication before touching any MCP server.
    Returns stage="validation_passed" or sets error and stage="invalid".
    """
    app: CustomerApplication = state["application"]
    errors = []

    if app.loan_amount <= 0:
        errors.append("loan_amount must be > 0")
    if app.loan_amount > 10_000_000:
        errors.append("loan_amount exceeds ₹1 Crore limit")
    if not (6 <= app.loan_tenure_months <= 360):
        errors.append("tenure must be 6–360 months")
    if app.monthly_income <= 0:
        errors.append("monthly_income must be > 0")
    if not app.pan_number or len(app.pan_number) != 10:
        errors.append("pan_number must be exactly 10 characters")
    if not app.mobile:
        errors.append("mobile is required")
    if not app.email:
        errors.append("email is required")

    if errors:
        return {"stage": "invalid", "error": "; ".join(errors)}

    return {"stage": "validation_passed"}


# ─────────────────────────────────────────────────────────────────────────────
# NODE 2 — run_agents  (ASYNC — LangGraph handles this natively)
# ─────────────────────────────────────────────────────────────────────────────

async def run_agents(state: dict) -> dict:
    """
    Fan out to all 5 specialist agents simultaneously using asyncio.gather.

    This is an async node — LangGraph's async execution mode handles it
    natively via graph.ainvoke() / graph.astream().

    Each agent:
      1. Calls its dedicated MCP server (mock or real)
      2. Interprets the response and scores it 0–100
      3. Returns an AgentResult with score + flags

    Fault tolerance:
      - asyncio.TimeoutError  → AGENT_TIMEOUT flag, neutral score 50.0
      - Any other Exception   → AGENT_ERROR  flag, neutral score 50.0
      - return_exceptions=True ensures one failure never cancels the others

    Total wall-clock latency ≈ max(individual latencies), not sum.
    """
    app: CustomerApplication = state["application"]

    agents: List[BaseAgent] = [
        DocumentVerificationAgent(),   # 20% weight — PAN, Aadhaar, docs
        CreditScoreAgent(),            # 35% weight — CIBIL bureau score
        IncomeAssessmentAgent(),       # 25% weight — bank statements, DTI
        RiskAssessmentAgent(),         # 15% weight — fraud ML, blacklist
        ComplianceAgent(),             #  5% weight — KYC, AML, sanctions
    ]

    tasks = [
        asyncio.wait_for(agent.process(app), timeout=settings.AGENT_TIMEOUT)
        for agent in agents
    ]

    raw = await asyncio.gather(*tasks, return_exceptions=True)

    results: List[AgentResult] = []
    for i, r in enumerate(raw):
        if isinstance(r, asyncio.TimeoutError):
            results.append(_fallback(agents[i], ["AGENT_TIMEOUT"],
                                     f"Agent timed out after {settings.AGENT_TIMEOUT}s"))
        elif isinstance(r, Exception):
            results.append(_fallback(agents[i], ["AGENT_ERROR"], str(r)))
        else:
            results.append(r)

    # Return new list — LangGraph's Annotated[List, operator.add] reducer
    # will append this to state["agent_results"] (which starts as [])
    return {"agent_results": results, "stage": "agents_complete"}


def _fallback(agent: BaseAgent, flags: list, error: str) -> AgentResult:
    return AgentResult(
        agent_name = agent.name,
        status     = AgentStatus.ERROR,
        score      = 50.0,
        weight     = agent.weight,
        flags      = flags,
        mcp_server = agent.mcp_url,
        mcp_result = {"error": error},
        latency_ms = 0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# NODE 3 — hard_stop_check
# ─────────────────────────────────────────────────────────────────────────────

def hard_stop_check(state: dict) -> dict:
    """
    Scan all agent flags for hard-stop codes.

    Hard stops bypass weighted scoring and force an immediate REJECT.
    If found, pre-builds the REJECT LoanDecision and stores it.
    The router will then skip score_and_decide entirely.

    Hard-stop codes:
      BLACKLIST_HIT      — internal / regulatory blacklist
      SANCTIONS_HIT      — OFAC / UN / EU sanctions match
      RBI_DEFAULTER      — RBI CRILC wilful defaulter list
      PAN_INVALID        — PAN not found in NSDL
      DTI_CRITICAL       — debt-to-income > 60% (unserviceable)
      FRAUD_RISK_CRITICAL — ML fraud model: CRITICAL band
    """
    results: List[AgentResult] = state.get("agent_results", [])
    all_flags  = [f for r in results for f in r.flags]
    hard_stops = [f for f in all_flags if f in HARD_STOP_FLAGS]

    if hard_stops:
        app: CustomerApplication = state["application"]
        decision = LoanDecision(
            application_id        = app.application_id,
            decision              = Decision.REJECT,
            final_score           = 0.0,
            agent_results         = results,
            reason_codes          = sorted(set(hard_stops)),
            human_review_required = False,
            total_latency_ms      = 0,
        )
        return {
            "hard_stop_flags": hard_stops,   # reducer appends these
            "decision":        decision,
            "stage":           "hard_stop_triggered",
        }

    return {"stage": "hard_stop_clear"}


# ─────────────────────────────────────────────────────────────────────────────
# NODE 4 — score_and_decide
# ─────────────────────────────────────────────────────────────────────────────

def score_and_decide(state: dict) -> dict:
    """
    Compute the weighted composite score and apply decision thresholds.

      composite = Σ(agent.score × agent.weight)
                = doc×0.20 + credit×0.35 + income×0.25 + risk×0.15 + compliance×0.05

    Thresholds (settings.py):
      ≥ 70  →  APPROVE  (with loan terms)
      50–69 →  REFER    (human underwriter review)
      < 50  →  REJECT

    Human-review flags (PEP_DETECTED, AML_FLAGGED, DOCUMENT_TAMPERED …)
    set human_review_required=True even on APPROVE — approval needs sign-off.
    """
    results: List[AgentResult] = state.get("agent_results", [])
    app: CustomerApplication   = state["application"]

    decision = _engine.decide(app, results, total_latency_ms=0)
    return {
        "decision": decision,
        "stage":    f"decided_{decision.decision.value.lower()}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 5 — human_review
# ─────────────────────────────────────────────────────────────────────────────

def human_review(state: dict) -> dict:
    """
    Human underwriter review node — only reached on the REFER path.

    In production with real LangGraph + a checkpointer (e.g. SqliteSaver):

        # Compile with interrupt so the graph PAUSES here:
        app = build_graph(checkpointer=SqliteSaver.from_conn_string(":memory:"),
                          interrupt_before=["human_review"])
        config = {"configurable": {"thread_id": "APP-001"}}

        # First run — pipeline pauses before human_review executes:
        await app.ainvoke(initial_state(application), config)

        # Underwriter reviews state, then resumes with their decision:
        app.update_state(config, {"human_review_approved": True})
        final = await app.ainvoke(None, config)

    Without a checkpointer, human_review_approved must be set in the
    initial state before calling invoke (simulated review).

    State field human_review_approved:
      True  → underwriter overrides to APPROVE (loan terms recalculated)
      False → underwriter confirms REJECT
      None  → application queued for review (stays REFER)
    """
    decision: LoanDecision = state["decision"]
    approved: bool | None  = state.get("human_review_approved")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    notes = (
        f"Referred at {ts}. Score: {decision.final_score:.1f}. "
        f"Flags: {', '.join(decision.reason_codes) or 'none'}."
    )

    if approved is True:
        terms = _engine._calculate_terms(state["application"], decision.final_score)
        new = LoanDecision(
            application_id        = decision.application_id,
            decision              = Decision.APPROVE,
            final_score           = decision.final_score,
            agent_results         = decision.agent_results,
            loan_terms            = terms,
            reason_codes          = decision.reason_codes + ["UNDERWRITER_APPROVED"],
            human_review_required = False,
            total_latency_ms      = decision.total_latency_ms,
        )
        return {"decision": new,
                "human_review_notes": notes + " → Manually APPROVED.",
                "stage": "human_approved"}

    if approved is False:
        new = LoanDecision(
            application_id        = decision.application_id,
            decision              = Decision.REJECT,
            final_score           = decision.final_score,
            agent_results         = decision.agent_results,
            reason_codes          = decision.reason_codes + ["UNDERWRITER_REJECTED"],
            human_review_required = False,
            total_latency_ms      = decision.total_latency_ms,
        )
        return {"decision": new,
                "human_review_notes": notes + " → Manually REJECTED.",
                "stage": "human_rejected"}

    # None → still pending
    return {"human_review_notes": notes + " Awaiting underwriter decision.",
            "stage": "human_review_queued"}


# ─────────────────────────────────────────────────────────────────────────────
# NODE 6 — format_response
# ─────────────────────────────────────────────────────────────────────────────

def format_response(state: dict) -> dict:
    """
    Final node — always reached before END.
    Computes total latency from sum of all agent latencies.
    """
    decision: LoanDecision = state.get("decision")
    if decision is None:
        return {"stage": "error", "error": "No decision produced — pipeline bug."}

    decision.total_latency_ms = sum(r.latency_ms for r in decision.agent_results)
    return {"decision": decision, "stage": "complete"}


# ─────────────────────────────────────────────────────────────────────────────
# ROUTER FUNCTIONS  (used with graph.add_conditional_edges)
# ─────────────────────────────────────────────────────────────────────────────

def route_after_validation(state: dict) -> str:
    """'run_agents' if valid, 'invalid' (→ END) if not."""
    return "invalid" if state.get("error") else "run_agents"


def route_after_hard_stop(state: dict) -> str:
    """'reject' (→ format_response) if hard stop found, else 'continue' (→ score_and_decide)."""
    return "reject" if state.get("hard_stop_flags") else "continue"


def route_after_score(state: dict) -> str:
    """'APPROVE', 'REFER', or 'REJECT' — maps directly to edge keys."""
    d: LoanDecision = state.get("decision")
    return d.decision.value if d else "REJECT"
