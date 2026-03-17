"""
mcp_servers/base.py
===================
Base class for all MCP servers.

Each MCP server is a real FastAPI microservice on its own port.
  MOCK_DATA=true  → _mock_response() returns seeded fixtures
  MOCK_DATA=false → _real_response() calls real external APIs

Server ports (defaults, overridable via env):
  document-verification-mcp  → 8001
  credit-bureau-mcp          → 8002
  bank-statement-mcp         → 8003
  risk-engine-mcp            → 8004
  compliance-mcp             → 8005

HTTP API (every server exposes the same contract):
  POST /call    → { "tool": "...", "params": { ... } }
  GET  /health  → { "status": "healthy", "server": "...", "mode": "mock|real" }
  GET  /tools   → list of available tool names
"""

# No "from __future__ import annotations" — Pydantic v2 needs real types.

import asyncio
import random
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from core.models import MCPToolCall, MCPToolResult
from config.settings import settings


class BaseMCPServer(ABC):

    server_name: str  = "base-mcp"
    default_port: int = 8000
    MOCK_LATENCY_MIN: float = 0.05
    MOCK_LATENCY_MAX: float = 0.35

    def __init__(self):
        self.mock_mode = settings.MOCK_DATA

    # ── Internal call ──────────────────────────────────────────────────────

    async def call(self, tool_call: MCPToolCall) -> MCPToolResult:
        start = time.perf_counter()
        try:
            if self.mock_mode:
                await asyncio.sleep(
                    random.uniform(self.MOCK_LATENCY_MIN, self.MOCK_LATENCY_MAX)
                )
                raw = await self._mock_response(tool_call)
            else:
                raw = await self._real_response(tool_call)

            return MCPToolResult(
                tool       = tool_call.tool,
                server     = self.server_name,
                success    = True,
                data       = raw,
                latency_ms = int((time.perf_counter() - start) * 1000),
                mock_mode  = self.mock_mode,
            )
        except Exception as exc:
            return MCPToolResult(
                tool       = tool_call.tool,
                server     = self.server_name,
                success    = False,
                data       = {},
                error      = str(exc),
                latency_ms = int((time.perf_counter() - start) * 1000),
                mock_mode  = self.mock_mode,
            )

    # ── FastAPI HTTP server ────────────────────────────────────────────────

    def serve(self, host: str = "0.0.0.0", port: Optional[int] = None,
              log_level: str = "info"):
        import uvicorn
        app = self._build_app()
        uvicorn.run(app, host=host, port=port or self.default_port,
                    log_level=log_level)

    def _build_app(self):
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse

        app = FastAPI(title=self.server_name, version="1.0.0")
        server_ref = self

        @app.post("/call")
        async def call_tool(request: Request):
            """
            Accept raw JSON body — bypasses Pydantic model validation entirely.
            This is the most compatible approach across all Pydantic/Python versions.
            """
            try:
                body = await request.json()
            except Exception:
                return JSONResponse(status_code=400,
                                    content={"error": "Invalid JSON body"})

            tool       = body.get("tool", "")
            params     = body.get("params", {}) or {}
            session_id = body.get("session_id", "")

            if not tool:
                return JSONResponse(status_code=400,
                                    content={"error": "Missing required field: tool"})

            tool_call  = MCPToolCall(tool=tool, params=params,
                                     session_id=session_id)
            mcp_result = await server_ref.call(tool_call)
            return {
                "tool":       mcp_result.tool,
                "server":     mcp_result.server,
                "success":    mcp_result.success,
                "data":       mcp_result.data,
                "error":      mcp_result.error,
                "latency_ms": mcp_result.latency_ms,
                "mock_mode":  mcp_result.mock_mode,
            }

        @app.get("/health")
        async def health():
            return {
                "status": "healthy",
                "server": server_ref.server_name,
                "mode":   "mock" if server_ref.mock_mode else "real",
                "tools":  server_ref.tools(),
            }

        @app.get("/tools")
        async def list_tools():
            return {"server": server_ref.server_name, "tools": server_ref.tools()}

        return app

    # ── Subclass contract ──────────────────────────────────────────────────

    @abstractmethod
    async def _mock_response(self, tool_call: MCPToolCall) -> Dict[str, Any]:
        """Return deterministic mock data."""

    async def _real_response(self, tool_call: MCPToolCall) -> Dict[str, Any]:
        raise NotImplementedError(
            f"{self.server_name}: real API not implemented. "
            "Set MOCK_DATA=true or implement _real_response()."
        )

    def tools(self) -> List[str]:
        return []

    def _seed(self, *values) -> int:
        combined = "".join(str(v) for v in values)
        return sum(ord(c) * (i + 1) for i, c in enumerate(combined))
