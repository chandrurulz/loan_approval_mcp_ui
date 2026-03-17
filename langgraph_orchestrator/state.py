"""
langgraph_orchestrator/state.py
================================
Typed state for the LangGraph loan approval pipeline.

LangGraph passes this TypedDict through every node.
Each node receives the full state and returns only the keys it updates —
LangGraph merges partial updates automatically via the Annotated reducer pattern.
"""

from __future__ import annotations

import operator
import uuid
from typing import Annotated, Any, Dict, List, Optional

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict

from core.models import AgentResult, CustomerApplication, LoanDecision


class LoanState(TypedDict):
    """
    Shared state that flows through every node in the LangGraph StateGraph.

    Fields with Annotated[List, operator.add] use LangGraph's reducer:
    instead of overwriting, each node's returned list is APPENDED to the
    existing list. This is the canonical LangGraph pattern for collecting
    results from parallel branches.
    """

    # ── Input ──────────────────────────────────────────────────────────────
    application: CustomerApplication          # Set once at init, read-only thereafter

    # ── Agent outputs (reducer: lists accumulate across nodes) ─────────────
    agent_results:   Annotated[List[AgentResult], operator.add]
    hard_stop_flags: Annotated[List[str], operator.add]

    # ── Decision ───────────────────────────────────────────────────────────
    decision: Optional[LoanDecision]

    # ── Human review (REFER path) ──────────────────────────────────────────
    human_review_notes:    str
    human_review_approved: Optional[bool]   # True=approve, False=reject, None=pending

    # ── Pipeline metadata ──────────────────────────────────────────────────
    error:  Optional[str]
    stage:  str
    run_id: str


def initial_state(application: CustomerApplication, run_id: str = "") -> dict:
    """
    Build the initial state dict to pass into graph.invoke() / graph.ainvoke().

    Usage:
        state  = initial_state(my_application)
        result = await loan_approval_graph.ainvoke(state)
        decision = result["decision"]
    """
    return {
        "application":           application,
        "agent_results":         [],
        "hard_stop_flags":       [],
        "decision":              None,
        "human_review_notes":    "",
        "human_review_approved": None,
        "error":                 None,
        "stage":                 "init",
        "run_id":                run_id or uuid.uuid4().hex[:8].upper(),
    }
