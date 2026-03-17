"""
agents/base.py
==============
Abstract base class for all loan processing agents.

Agents call their MCP server over HTTP.
  MOCK_DATA=true  → MCP server responds with mock data
  MOCK_DATA=false → MCP server calls real external APIs
  Either way, agent code is identical.
"""

from __future__ import annotations

import traceback
import time
from abc import ABC, abstractmethod

import httpx

from core.models import AgentResult, AgentStatus, CustomerApplication, MCPToolCall, MCPToolResult
from config.settings import settings


class BaseAgent(ABC):

    name:    str   = "BaseAgent"
    weight:  float = 0.20
    mcp_url: str   = ""

    async def process(self, application: CustomerApplication) -> AgentResult:
        start = time.perf_counter()
        try:
            tool_call  = self._build_tool_call(application)
            mcp_result = await self._http_call(tool_call)

            if not mcp_result.success:
                return self._error_result(
                    mcp_result.error or "MCP call failed",
                    int((time.perf_counter() - start) * 1000),
                )

            score, flags = self._score(application, mcp_result.data)
            return AgentResult(
                agent_name = self.name,
                status     = AgentStatus.PASS if score >= self._pass_threshold() else AgentStatus.FAIL,
                score      = round(max(min(score, 100.0), 0.0), 1),
                weight     = self.weight,
                flags      = flags,
                mcp_server = self.mcp_url,
                mcp_result = mcp_result.data,
                latency_ms = int((time.perf_counter() - start) * 1000),
            )

        except Exception as exc:
            # Print full traceback so errors are visible during development
            tb = traceback.format_exc()
            print(f"\n[{self.name}] ERROR:\n{tb}")
            return self._error_result(
                f"{type(exc).__name__}: {exc}",
                int((time.perf_counter() - start) * 1000),
            )

    async def _http_call(self, tool_call: MCPToolCall) -> MCPToolResult:
        url = f"{self.mcp_url}/call"
        payload = {
            "tool":       tool_call.tool,
            "params":     tool_call.params,
            "session_id": tool_call.session_id,
        }
        try:
            async with httpx.AsyncClient(timeout=settings.AGENT_TIMEOUT) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError:
            raise ConnectionError(
                f"Cannot connect to MCP server at {url}. "
                "Is 'MOCK_DATA=true python3 mcp_servers/run_servers.py' running?"
            )
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"MCP server {url} returned {exc.response.status_code}: "
                f"{exc.response.text[:300]}"
            )

        return MCPToolResult(
            tool      = data["tool"],
            server    = data["server"],
            success   = data["success"],
            data      = data.get("data", {}),
            error     = data.get("error"),
            mock_mode = data.get("mock_mode", True),
        )

    # ── Subclass contract ──────────────────────────────────────────────────

    @abstractmethod
    def _build_tool_call(self, application: CustomerApplication) -> MCPToolCall:
        """Construct the MCPToolCall for this agent's MCP server."""

    @abstractmethod
    def _score(self, application: CustomerApplication, data: dict) -> tuple[float, list[str]]:
        """Return (score 0-100, flags). Higher score = lower risk."""

    def _pass_threshold(self) -> float:
        return 50.0

    def _error_result(self, error: str, latency_ms: int) -> AgentResult:
        return AgentResult(
            agent_name = self.name,
            status     = AgentStatus.ERROR,
            score      = 50.0,
            weight     = self.weight,
            flags      = ["AGENT_ERROR"],
            mcp_server = self.mcp_url,
            mcp_result = {"error": error},
            latency_ms = latency_ms,
        )
