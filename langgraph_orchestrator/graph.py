"""
langgraph_orchestrator/graph.py
================================
Assembles the LangGraph StateGraph for the loan approval pipeline.

Install requirements:
    pip install langgraph langchain-core

Graph topology:
                       ┌──────────────────┐
                       │  validate_input  │  ← set_entry_point
                       └────────┬─────────┘
              validation_passed │   invalid
                       ┌────────┘          └──── END
                       ▼
                 ┌────────────┐
                 │ run_agents │  ← async node, 5 agents in parallel
                 └─────┬──────┘
                       │
                ┌──────▼──────────┐
                │ hard_stop_check │
                └──┬──────────────┘
           reject  │   continue
     ┌─────────────┘      └─────────────────┐
     ▼                                      ▼
┌─────────────────┐               ┌──────────────────┐
│ format_response │               │  score_and_decide │
└────────┬────────┘               └──┬──────┬─────────┘
         │                    APPROVE│    REFER│  REJECT│
         │                    ┌──────┘   ┌────┘        │
         │         ┌──────────▼──┐  ┌────▼──────┐      │
         │         │format_resp. │  │human_review│      │
         │         └──────┬──────┘  └─────┬──────┘      │
         │                │               │              │
         └────────────────┴───────────────┴──────────────┘
                                  │
                                 END
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END

from langgraph_orchestrator.state import LoanState
from langgraph_orchestrator.nodes import (
    validate_input,
    run_agents,
    hard_stop_check,
    score_and_decide,
    human_review,
    format_response,
    route_after_validation,
    route_after_hard_stop,
    route_after_score,
)


def build_graph(checkpointer=None, interrupt_before: list = None) -> StateGraph:
    """
    Build and compile the loan approval StateGraph.

    Args:
        checkpointer:     LangGraph checkpointer for persistence + HITL.
                          e.g. MemorySaver() or SqliteSaver.from_conn_string(":memory:")
                          Required for interrupt_before to work.

        interrupt_before: List of node names to pause before executing.
                          e.g. ["human_review"] for human-in-the-loop.

    Returns:
        Compiled LangGraph app supporting:
            .invoke(state)          — sync
            .ainvoke(state)         — async
            .stream(state)          — sync generator (per-node updates)
            .astream(state)         — async generator (per-node updates)
            .get_graph()            — graph introspection
            .get_graph().draw_mermaid_png()   — visual diagram

    Examples:

        # Simple async invocation:
        app = build_graph()
        result = await app.ainvoke(initial_state(my_application))

        # With human-in-the-loop (REFER path pauses for underwriter):
        from langgraph.checkpoint.memory import MemorySaver
        app = build_graph(
            checkpointer=MemorySaver(),
            interrupt_before=["human_review"]
        )
        config = {"configurable": {"thread_id": "APP-001"}}
        await app.ainvoke(initial_state(application), config)
        # Pipeline paused — underwriter reviews
        app.update_state(config, {"human_review_approved": True})
        final = await app.ainvoke(None, config)

        # Streaming — observe each node as it completes:
        async for chunk in app.astream(initial_state(application)):
            node_name, node_state = next(iter(chunk.items()))
            print(f"[{node_name}] stage={node_state.get('stage')}")
    """
    graph = StateGraph(LoanState)

    # ── Nodes ─────────────────────────────────────────────────────────────────
    graph.add_node("validate_input",   validate_input)
    graph.add_node("run_agents",       run_agents)        # async
    graph.add_node("hard_stop_check",  hard_stop_check)
    graph.add_node("score_and_decide", score_and_decide)
    graph.add_node("human_review",     human_review)
    graph.add_node("format_response",  format_response)

    # ── Entry ─────────────────────────────────────────────────────────────────
    graph.set_entry_point("validate_input")

    # ── Edges ─────────────────────────────────────────────────────────────────

    # validate_input → run_agents  OR  → END (invalid input)
    graph.add_conditional_edges(
        "validate_input",
        route_after_validation,
        {
            "run_agents": "run_agents",
            "invalid":    END,
        },
    )

    # run_agents → hard_stop_check  (always)
    graph.add_edge("run_agents", "hard_stop_check")

    # hard_stop_check → format_response  OR  → score_and_decide
    graph.add_conditional_edges(
        "hard_stop_check",
        route_after_hard_stop,
        {
            "reject":   "format_response",
            "continue": "score_and_decide",
        },
    )

    # score_and_decide → format_response | human_review | format_response
    graph.add_conditional_edges(
        "score_and_decide",
        route_after_score,
        {
            "APPROVE": "format_response",
            "REFER":   "human_review",
            "REJECT":  "format_response",
        },
    )

    # human_review → format_response  (always)
    graph.add_edge("human_review", "format_response")

    # format_response → END
    graph.add_edge("format_response", END)

    # ── Compile ────────────────────────────────────────────────────────────────
    kwargs = {}
    if checkpointer:
        kwargs["checkpointer"] = checkpointer
    if interrupt_before:
        kwargs["interrupt_before"] = interrupt_before

    return graph.compile(**kwargs)


# Module-level compiled graph — import and use directly:
#   from langgraph_orchestrator.graph import loan_approval_graph
loan_approval_graph = build_graph()
