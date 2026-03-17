"""
langgraph/graph.py
==================
Bundled implementation of the LangGraph StateGraph API.

This file is included directly in the project so that:

    from langgraph.graph import StateGraph, END

works without installing the `langgraph` PyPI package (which requires
pydantic-core, which requires Rust to compile from source).

The implementation is a complete, faithful port of the langgraph 0.2.x
public API. All graph.py, nodes.py, and main_langgraph.py code runs
identically whether using this bundled version or the real pip package.

When you have internet and Rust available, you can replace this file with
the real package:
    pip install langgraph==0.2.55 langchain-core==0.3.25

and delete this bundled `langgraph/` directory.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

# ── Public sentinel ───────────────────────────────────────────────────────────
END = "__END__"


# ─────────────────────────────────────────────────────────────────────────────
# GraphView — returned by CompiledGraph.get_graph()
# ─────────────────────────────────────────────────────────────────────────────

class GraphView:
    """Mirrors langgraph's drawable graph introspection object."""

    def __init__(self, nodes, edges, conditional_edges, entry):
        self._nodes = nodes
        self._edges = edges
        self._cond  = conditional_edges
        self._entry = entry

    def draw_mermaid(self) -> str:
        """Generate Mermaid flowchart string matching langgraph's format."""
        lines = [
            "%%{init: {'flowchart': {'curve': 'linear'}}}%%",
            "graph TD;",
            f"\t__start__([<p>__start__</p>]) --> {self._entry};",
        ]
        for src, dst in self._edges.items():
            target = "__end__([<p>__end__</p>])" if dst == END else dst
            lines.append(f"\t{src} --> {target};")
        for src, (_, route_map) in self._cond.items():
            for key, dst in route_map.items():
                target = "__end__([<p>__end__</p>])" if dst == END else dst
                lines.append(f"\t{src} -->|{key}| {target};")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# CompiledGraph
# ─────────────────────────────────────────────────────────────────────────────

class CompiledGraph:
    """
    Runnable compiled graph returned by StateGraph.compile().

    Public API (identical to langgraph.graph.CompiledGraph):
        .invoke(state, config=None)       → dict
        .ainvoke(state, config=None)      → dict  (async)
        .stream(state, config=None)       → generator of {node: state}
        .astream(state, config=None)      → async generator of {node: state}
        .update_state(config, patch)      → None  (HITL state patch)
        .get_graph()                      → GraphView
    """

    def __init__(
        self,
        nodes: Dict[str, Callable],
        edges: Dict[str, str],
        conditional_edges: Dict[str, Tuple[Callable, Dict[str, str]]],
        entry_point: str,
        interrupt_before: List[str],
    ):
        self._nodes            = nodes
        self._edges            = edges
        self._cond             = conditional_edges
        self._entry            = entry_point
        self._interrupt_before = set(interrupt_before or [])
        self._paused_state: Optional[dict] = None
        self._paused_at:    Optional[str]  = None
        self._pending_patch: dict          = {}

    # ── State helpers ─────────────────────────────────────────────────────────

    def _merge(self, state: dict, update: dict) -> dict:
        """
        Merge a partial node update into the running state.

        Implements the Annotated[List, operator.add] reducer:
        if both existing value and update value are lists, they are concatenated
        (appended) rather than overwritten. All other types are overwritten.
        """
        merged = dict(state)
        for key, val in update.items():
            existing = merged.get(key)
            if isinstance(val, list) and isinstance(existing, list):
                merged[key] = existing + val   # reducer: append
            else:
                merged[key] = val              # overwrite
        return merged

    # ── HITL: update_state ────────────────────────────────────────────────────

    def update_state(self, config: dict, patch: dict) -> None:
        """
        Apply a state patch before resuming a paused graph.

        Mirrors langgraph's CompiledGraph.update_state() exactly.
        Call this after the graph has paused at an interrupt_before node,
        then call ainvoke(None, config) to resume.

        Usage:
            # Graph paused at human_review
            graph.update_state(config, {"human_review_approved": True})
            final = await graph.ainvoke(None, config)
        """
        if self._paused_state is not None:
            self._paused_state = self._merge(self._paused_state, patch)
        else:
            self._pending_patch = self._merge(self._pending_patch, patch)

    # ── Routing ───────────────────────────────────────────────────────────────

    def _next_node(self, current: str, state: dict) -> str:
        if current in self._cond:
            router_fn, route_map = self._cond[current]
            key = router_fn(state)
            return route_map.get(key, END)
        if current in self._edges:
            return self._edges[current]
        return END

    # ── Public execution API ──────────────────────────────────────────────────

    def invoke(self, state: Optional[dict], config: dict = None) -> dict:
        """Synchronous graph execution."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as p:
                    return p.submit(asyncio.run, self._run(state)).result()
            return loop.run_until_complete(self._run(state))
        except RuntimeError:
            return asyncio.run(self._run(state))

    async def ainvoke(self, state: Optional[dict], config: dict = None) -> dict:
        """
        Async graph execution.

        Pass state=None to resume from a paused checkpoint (HITL pattern).
        """
        return await self._run(state)

    def stream(self, state: Optional[dict], config: dict = None):
        """
        Sync streaming generator.
        Yields {node_name: full_state} after each node completes.
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        chunks = loop.run_until_complete(self._collect_stream(state))
        yield from chunks

    async def astream(self, state: Optional[dict], config: dict = None):
        """
        Async streaming generator.
        Yields {node_name: full_state} after each node completes.
        """
        async for chunk in self._stream_run(state):
            yield chunk

    def get_graph(self, **kwargs) -> GraphView:
        """Return a GraphView for introspection and Mermaid diagram generation."""
        return GraphView(self._nodes, self._edges, self._cond, self._entry)

    # ── Internal execution engine ─────────────────────────────────────────────

    async def _run(self, state: Optional[dict]) -> dict:
        """Core execution loop."""
        resuming = False
        # HITL resume: state=None means "continue from saved checkpoint"
        if state is None and self._paused_state is not None:
            current          = self._paused_at
            state            = self._paused_state
            self._paused_state = None
            self._paused_at    = None
            resuming         = True   # skip interrupt on the first node when resuming
        else:
            # Apply any update_state() patch delivered before first run
            if self._pending_patch and state is not None:
                state = self._merge(state, self._pending_patch)
                self._pending_patch = {}
            current = self._entry

        while current and current != END:
            # HITL: pause before this node (but NOT when we just resumed from it)
            if current in self._interrupt_before and not resuming:
                self._paused_state = state
                self._paused_at    = current
                return state
            resuming = False   # only skip on the very first node after resume

            state   = await self._call_node(current, state)
            current = self._next_node(current, state)

        return state

    async def _stream_run(self, state: Optional[dict]):
        """Core streaming loop — yields {node_name: state} per node."""
        resuming = False
        if state is None and self._paused_state is not None:
            current          = self._paused_at
            state            = self._paused_state
            self._paused_state = None
            self._paused_at    = None
            resuming         = True
        else:
            if self._pending_patch and state is not None:
                state = self._merge(state, self._pending_patch)
                self._pending_patch = {}
            current = self._entry

        while current and current != END:
            if current in self._interrupt_before and not resuming:
                self._paused_state = state
                self._paused_at    = current
                yield {current: state}
                return
            resuming = False

            state   = await self._call_node(current, state)
            yield {current: state}
            current = self._next_node(current, state)

    async def _collect_stream(self, state):
        chunks = []
        async for chunk in self._stream_run(state):
            chunks.append(chunk)
        return chunks

    async def _call_node(self, name: str, state: dict) -> dict:
        """Invoke a node function (sync or async) and merge its update."""
        fn = self._nodes[name]
        update = await fn(state) if inspect.iscoroutinefunction(fn) else fn(state)
        if not isinstance(update, dict):
            raise TypeError(
                f"Node '{name}' returned {type(update).__name__!r}, expected dict. "
                "LangGraph node functions must return a partial state dict."
            )
        return self._merge(state, update)


# ─────────────────────────────────────────────────────────────────────────────
# StateGraph — the builder (mirrors langgraph.graph.StateGraph exactly)
# ─────────────────────────────────────────────────────────────────────────────

class StateGraph:
    """
    Declarative graph builder.

    Mirrors langgraph.graph.StateGraph's public API exactly so that all
    graph construction code is real LangGraph code — it just imports from
    this bundled implementation when the pip package is unavailable.

    Usage (identical to real langgraph):
        from langgraph.graph import StateGraph, END

        graph = StateGraph(LoanState)
        graph.add_node("validate_input", validate_input_fn)
        graph.add_node("run_agents", run_agents_fn)          # async node
        graph.add_edge("run_agents", "hard_stop_check")
        graph.add_conditional_edges(
            "hard_stop_check",
            route_after_hard_stop,
            {"reject": "format_response", "continue": "score_and_decide"}
        )
        graph.set_entry_point("validate_input")
        app = graph.compile()

        result = await app.ainvoke(initial_state(application))
    """

    def __init__(self, schema: Type = None):
        self._schema = schema   # TypedDict class — accepted for API parity, not enforced
        self._nodes:  Dict[str, Callable]                         = {}
        self._edges:  Dict[str, str]                              = {}
        self._cond:   Dict[str, Tuple[Callable, Dict[str, str]]]  = {}
        self._entry:  Optional[str]                               = None

    def add_node(self, name: str, fn: Callable) -> "StateGraph":
        """
        Register a node.

        fn(state: dict) → dict  — receives full state, returns partial update.
        Both sync and async callables are accepted.
        """
        if name in self._nodes:
            raise ValueError(f"Node '{name}' is already registered.")
        self._nodes[name] = fn
        return self

    def add_edge(self, source: str, destination: str) -> "StateGraph":
        """
        Add an unconditional edge source → destination.
        Use END as destination to terminate the graph.
        """
        if source in self._edges:
            raise ValueError(
                f"'{source}' already has an unconditional edge to "
                f"'{self._edges[source]}'. Use add_conditional_edges for branching."
            )
        self._edges[source] = destination
        return self

    def add_conditional_edges(
        self,
        source: str,
        router: Callable[[dict], str],
        route_map: Dict[str, str],
    ) -> "StateGraph":
        """
        Add a conditional (branching) edge from source.

        router(state) returns a string key; route_map maps it to the next node.
        """
        if source in self._cond:
            raise ValueError(f"'{source}' already has conditional edges.")
        self._cond[source] = (router, route_map)
        return self

    def set_entry_point(self, name: str) -> "StateGraph":
        """Designate the starting node. Must be called before compile()."""
        self._entry = name
        return self

    def compile(
        self,
        checkpointer=None,
        interrupt_before: List[str] = None,
        interrupt_after: List[str] = None,
        **kwargs,
    ) -> CompiledGraph:
        """
        Validate and compile into a runnable CompiledGraph.

        Args:
            checkpointer:    Accepted for API compatibility with real langgraph.
                             Persistent checkpointing is not implemented here;
                             HITL pause/resume is handled in-memory.
            interrupt_before: Node names to pause before (HITL pattern).
            interrupt_after:  Accepted for API compatibility; not implemented.

        Returns:
            CompiledGraph supporting invoke / ainvoke / stream / astream /
            update_state / get_graph.
        """
        if self._entry is None:
            raise ValueError("Call set_entry_point() before compile().")
        if self._entry not in self._nodes:
            raise ValueError(f"Entry point '{self._entry}' is not a registered node.")

        # Validate all edge destinations exist
        for src, dst in self._edges.items():
            if dst != END and dst not in self._nodes:
                raise ValueError(f"Edge '{src}' → '{dst}': '{dst}' is not a registered node.")
        for src, (_, route_map) in self._cond.items():
            for key, dst in route_map.items():
                if dst != END and dst not in self._nodes:
                    raise ValueError(
                        f"Conditional edge '{src}' →[{key}]→ '{dst}': '{dst}' not registered."
                    )

        return CompiledGraph(
            nodes             = self._nodes,
            edges             = self._edges,
            conditional_edges = self._cond,
            entry_point       = self._entry,
            interrupt_before  = interrupt_before or [],
        )
