#!/usr/bin/env python3
"""
langgraph_orchestrator/main_langgraph.py
=========================================
Demo runner for the LangGraph loan approval pipeline.

Install:
    pip install langgraph langchain-core

Run:
    MOCK_DATA=true python3 langgraph_orchestrator/main_langgraph.py
    MOCK_DATA=true python3 langgraph_orchestrator/main_langgraph.py --stream
    MOCK_DATA=true python3 langgraph_orchestrator/main_langgraph.py --hitl
    MOCK_DATA=true python3 langgraph_orchestrator/main_langgraph.py --mermaid
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MOCK_DATA", "true")

from langgraph_orchestrator.graph import build_graph, loan_approval_graph
from langgraph_orchestrator.state import initial_state
from core.models import CustomerApplication, Decision, LoanDecision, LoanPurpose, EmploymentType

# ── ANSI colours ──────────────────────────────────────────────────────────────
def bold(t):   return f"\033[1m{t}\033[0m"
def cyan(t):   return f"\033[36m{t}\033[0m"
def green(t):  return f"\033[32m{t}\033[0m"
def yellow(t): return f"\033[33m{t}\033[0m"
def red(t):    return f"\033[31m{t}\033[0m"
def dim(t):    return f"\033[2m{t}\033[0m"
SEP  = "═" * 70
SEP2 = "─" * 70

# ── Test applications ─────────────────────────────────────────────────────────
TEST_APPS = [
    CustomerApplication(
        customer_name="Priya Sharma",        pan_number="ABCPS1234P",
        aadhaar_number="9876-5432-1098",     date_of_birth="1988-04-15",
        mobile="9876543210",                 email="priya.sharma@gmail.com",
        loan_amount=500_000,                 loan_tenure_months=36,
        loan_purpose=LoanPurpose.HOME_RENOVATION,
        monthly_income=85_000,               employer_name="Tata Consultancy Services",
        employment_type=EmploymentType.SALARIED, years_of_employment=6.5,
        residential_address="42 MG Road, Bengaluru",
    ),
    CustomerApplication(
        customer_name="Zubair Ali Khan",     pan_number="ZZXZA9999Z",
        aadhaar_number="1234-5678-9012",     date_of_birth="1975-11-30",
        mobile="9123456780",                 email="zubair.khan@company.com",
        loan_amount=1_500_000,               loan_tenure_months=60,
        loan_purpose=LoanPurpose.BUSINESS,
        monthly_income=180_000,              employer_name="Self-Employed",
        employment_type=EmploymentType.SELF_EMPLOYED, years_of_employment=10.0,
        residential_address="15 Juhu Tara Road, Mumbai",
    ),
    CustomerApplication(
        customer_name="Fraudster One",       pan_number="FAKEX0000X",
        aadhaar_number="0000-0000-0001",     date_of_birth="1990-01-01",
        mobile="0000000001",                 email="hacker@fraud.com",
        loan_amount=2_000_000,               loan_tenure_months=24,
        monthly_income=10_000,               employer_name="Unknown Corp",
        residential_address="Unknown",
    ),
    CustomerApplication(
        customer_name="Rahul Mehta",         pan_number="ABCRM5678M",
        aadhaar_number="5555-6666-7777",     date_of_birth="1982-07-20",
        mobile="8765432190",                 email="rahul.mehta@infosys.com",
        loan_amount=3_000_000,               loan_tenure_months=120,
        loan_purpose=LoanPurpose.HOME_PURCHASE,
        monthly_income=150_000,              employer_name="Infosys Limited",
        employment_type=EmploymentType.SALARIED, years_of_employment=12.0,
        residential_address="78 Sector 15, Noida",
    ),
]


# ── Display helpers ───────────────────────────────────────────────────────────

def print_agent_results(results):
    for r in results:
        s = r.score
        score_str = (green if s >= 70 else yellow if s >= 50 else red)(f"{s:5.1f}")
        status    = (green("[PASS]") if r.status.value == "pass" else
                     red("[FAIL]")   if r.status.value == "fail" else yellow("[ERR ]"))
        flags_str = f"  → {yellow(', '.join(r.flags))}" if r.flags else ""
        print(f"  {status}  {r.agent_name:<38} score={score_str}  {dim(r.mcp_server)}{flags_str}")


def print_decision(state: dict):
    d: LoanDecision = state.get("decision")
    if not d:
        print(f"\n{red('ERROR:')} {state.get('error', 'unknown')}")
        return

    dstr = (green("✅  APPROVED") if d.decision == Decision.APPROVE else
            yellow("🔄  REFERRED") if d.decision == Decision.REFER  else
            red("❌  REJECTED"))

    print(f"\n{dstr}  {bold('Score:')} {d.final_score:.1f}  |  {d.total_latency_ms}ms")
    if d.loan_terms:
        t = d.loan_terms
        print(f"  {bold('Amount:')} ₹{t.approved_amount:,.0f}  "
              f"{bold('Rate:')} {t.interest_rate_pa}% p.a.  "
              f"{bold('EMI:')} ₹{t.emi_amount:,.0f}/mo  "
              f"{bold('Tenure:')} {t.tenure_months}mo")
        print(f"  Fee: ₹{t.processing_fee:,.0f}  |  Total repayable: ₹{t.total_repayable:,.0f}")
    if d.reason_codes:
        print(f"  {bold('Flags:')} {yellow(', '.join(d.reason_codes))}")
    if d.human_review_required:
        print(f"  {yellow('⚠  Human underwriter review required')}")
    if state.get("human_review_notes"):
        print(f"  {dim(state['human_review_notes'])}")


def print_summary(results_and_apps):
    print(f"\n{SEP}\n  {bold('BATCH SUMMARY')}\n{SEP2}")
    print(f"  {'Application ID':<16}  {'Customer':<22}  {'Decision':<10}  {'Score':>6}  {'Amount':>14}  {'ms':>6}")
    print(f"  {'─'*16}  {'─'*22}  {'─'*10}  {'─'*6}  {'─'*14}  {'─'*6}")
    for state, app in results_and_apps:
        d: LoanDecision = state.get("decision")
        if not d:
            continue
        dec = (green if d.decision == Decision.APPROVE else
               yellow if d.decision == Decision.REFER  else red)(f"{d.decision.value:<10}")
        amt = f"₹{d.loan_terms.approved_amount:,.0f}" if d.loan_terms else "—"
        print(f"  {d.application_id:<16}  {app.customer_name:<22}  {dec}  "
              f"{d.final_score:6.1f}  {amt:>14}  {d.total_latency_ms:>4}ms")


# ── Demo modes ────────────────────────────────────────────────────────────────

async def demo_standard():
    """Run all 4 test applications through the LangGraph pipeline."""
    print(f"\n{SEP}")
    print(f"  {bold(cyan('Loan Approval — LangGraph StateGraph'))}")
    print(f"  Nodes: validate_input → run_agents → hard_stop_check")
    print(f"         → score_and_decide → [human_review] → format_response → END")
    print(SEP)

    pairs = []
    for app in TEST_APPS:
        print(f"\n{SEP2}")
        print(f"  {bold('Application:')} {cyan(app.application_id)}  "
              f"{bold('Customer:')} {app.customer_name}")
        print(f"  {bold('Loan:')} ₹{app.loan_amount:,.0f} × {app.loan_tenure_months}mo  "
              f"| Income: ₹{app.monthly_income:,.0f}/mo  ({app.employer_name})")
        print(SEP2)

        state = await loan_approval_graph.ainvoke(initial_state(app))
        pairs.append((state, app))

        print_agent_results(state.get("agent_results", []))
        print_decision(state)

    print_summary(pairs)

    # JSON dump of first approved decision
    approved = next((s for s, _ in pairs if s.get("decision") and
                     s["decision"].decision == Decision.APPROVE), None)
    if approved:
        d = approved["decision"]
        print(f"\n{SEP}\n  {bold('JSON OUTPUT')} — {d.application_id}\n{SEP2}")
        print(json.dumps(d.summary(), indent=2))


async def demo_stream():
    """Stream node-by-node state updates using graph.astream()."""
    print(f"\n{SEP}")
    print(f"  {bold(cyan('LangGraph Streaming Mode — graph.astream()'))}")
    print(f"  Yields one {{node_name: state}} chunk per node as it completes")
    print(SEP)

    app = TEST_APPS[0]
    print(f"\n  Processing: {bold(app.customer_name)}\n")

    final_state = {}
    async for chunk in loan_approval_graph.astream(initial_state(app)):
        # LangGraph yields {node_name: full_state_after_node}
        node_name, node_state = next(iter(chunk.items()))
        stage = node_state.get("stage", "")

        colour = (green  if "passed" in stage or "clear" in stage or "approve" in stage else
                  yellow if "refer"  in stage or "human" in stage else
                  red    if "reject" in stage or "stop"  in stage or "invalid" in stage else
                  cyan)

        print(f"  {dim('▶')} {colour(bold(node_name)):<40} {dim('stage='+ stage)}")

        # Print agent results when run_agents completes
        if node_name == "run_agents":
            print_agent_results(node_state.get("agent_results", []))

        final_state = node_state

    print()
    print_decision(final_state)


async def demo_hitl():
    """
    Human-in-the-loop demo using LangGraph's MemorySaver checkpointer.

    When interrupt_before=["human_review"] is set:
      1. Graph runs until it reaches human_review node — then PAUSES
      2. We inspect the state (underwriter reviews it)
      3. We resume by calling ainvoke(None, config) with updated state

    This is the production pattern for the REFER path.
    """
    print(f"\n{SEP}")
    print(f"  {bold(cyan('Human-in-the-Loop Demo — MemorySaver + interrupt_before'))}")
    print(f"  Application: Rahul Mehta  (Low credit score → REFER → underwriter override)")
    print(SEP)

    # Import MemorySaver — requires langgraph installed
    from langgraph.checkpoint.memory import MemorySaver

    # Build graph with checkpointer + interrupt before human_review
    hitl_graph = build_graph(
        checkpointer=MemorySaver(),
        interrupt_before=["human_review"],
    )

    app    = TEST_APPS[3]   # Rahul Mehta → REFER (score 60.5)
    config = {"configurable": {"thread_id": app.application_id}}

    # ── Step 1: Run until paused ───────────────────────────────────────────
    print(f"\n  {bold('Step 1:')} Running pipeline — pauses before human_review node")
    state1 = await hitl_graph.ainvoke(initial_state(app), config)

    d = state1.get("decision")
    if d:
        print(f"  Pipeline paused at: {yellow(bold('human_review'))}")
        print(f"  Current decision:   {yellow(d.decision.value)}  |  "
              f"Score: {d.final_score:.1f}  |  "
              f"Flags: {', '.join(d.reason_codes)}")

    # ── Step 2: Underwriter reviews and overrides ──────────────────────────
    print(f"\n  {bold('Step 2:')} Underwriter reviews — overriding to APPROVE")
    hitl_graph.update_state(config, {"human_review_approved": True})

    # ── Step 3: Resume — pipeline continues from human_review ─────────────
    print(f"\n  {bold('Step 3:')} Resuming pipeline from human_review node")
    final = await hitl_graph.ainvoke(None, config)

    print()
    print_decision(final)


def demo_mermaid():
    """Print the Mermaid diagram generated by LangGraph's get_graph()."""
    print(f"\n{SEP}")
    print(f"  {bold(cyan('LangGraph Mermaid Diagram — graph.get_graph().draw_mermaid()'))}")
    print(SEP)
    try:
        mermaid = loan_approval_graph.get_graph().draw_mermaid()
        print("\nPaste into https://mermaid.live to visualise:\n")
        print(mermaid)
    except Exception as e:
        # Fallback hardcoded diagram if draw_mermaid() not available
        print("\n" + """
%%{init: {'flowchart': {'curve': 'linear'}}}%%
graph TD;
    __start__([START]) --> validate_input;
    validate_input -->|run_agents| run_agents;
    validate_input -->|invalid| __end__([END]);
    run_agents --> hard_stop_check;
    hard_stop_check -->|reject| format_response;
    hard_stop_check -->|continue| score_and_decide;
    score_and_decide -->|APPROVE| format_response;
    score_and_decide -->|REFER| human_review;
    score_and_decide -->|REJECT| format_response;
    human_review --> format_response;
    format_response --> __end__;
""")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--mermaid" in args:
        demo_mermaid()
    elif "--stream" in args:
        asyncio.run(demo_stream())
    elif "--hitl" in args:
        asyncio.run(demo_hitl())
    else:
        asyncio.run(demo_standard())
