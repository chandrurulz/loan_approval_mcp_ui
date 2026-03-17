"""
langgraph/checkpoint/memory.py
================================
Bundled MemorySaver — matches the real langgraph.checkpoint.memory.MemorySaver
API so that:

    from langgraph.checkpoint.memory import MemorySaver

works without the pip package.

The real MemorySaver persists graph state to an in-memory dict keyed by
thread_id, enabling pause/resume across ainvoke() calls. Our CompiledGraph
already handles HITL pause/resume internally (via _paused_state), so
MemorySaver here is a no-op sentinel accepted by build_graph(checkpointer=...)
for full API compatibility.
"""


class MemorySaver:
    """
    In-memory checkpointer. Accepted by StateGraph.compile(checkpointer=MemorySaver()).

    In the bundled langgraph implementation, HITL pause/resume is managed
    inside CompiledGraph via _paused_state / _paused_at. The checkpointer
    argument is accepted for API compatibility with real langgraph but is not
    used for actual persistence in this bundled version.

    Usage (identical to real langgraph):
        from langgraph.checkpoint.memory import MemorySaver

        app = build_graph(
            checkpointer=MemorySaver(),
            interrupt_before=["human_review"]
        )
        config = {"configurable": {"thread_id": "APP-001"}}

        # First run — graph pauses at human_review
        await app.ainvoke(initial_state(application), config)

        # Underwriter approves
        app.update_state(config, {"human_review_approved": True})

        # Resume
        final = await app.ainvoke(None, config)
    """

    def __init__(self):
        self._store: dict = {}   # thread_id → state  (for API completeness)

    def get(self, config: dict):
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        return self._store.get(thread_id)

    def put(self, config: dict, state: dict):
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        self._store[thread_id] = state
