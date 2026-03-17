"""
agents/orchestrator.py
=======================
Orchestrator Agent — the master controller of the loan approval pipeline.

Responsibilities:
  1. Receive a CustomerApplication from the API gateway
  2. Fan out to all 5 specialist agents concurrently (asyncio.gather)
  3. Apply per-agent timeouts (configurable via settings)
  4. Handle individual agent failures gracefully (circuit breaker)
  5. Pass collected AgentResults to DecisionEngine
  6. Return a LoanDecision with full audit trail

Design:
  ┌─────────────────────────────────────────────┐
  │              OrchestratorAgent              │
  │                                             │
  │  receive(CustomerApplication)               │
  │        │                                    │
  │        ├── asyncio.gather(timeout) ────►    │
  │        │       DocAgent                     │
  │        │       CreditAgent                  │
  │        │       IncomeAgent                  │
  │        │       RiskAgent                    │
  │        │       ComplianceAgent              │
  │        │                                    │
  │        └── DecisionEngine.decide()          │
  │              → LoanDecision                 │
  └─────────────────────────────────────────────┘

Timeout behaviour:
  - Each agent has AGENT_TIMEOUT seconds (default: 10s)
  - On timeout: agent gets neutral score=50, flag=AGENT_TIMEOUT
  - Pipeline NEVER blocks waiting for a single agent
"""

from __future__ import annotations

import asyncio
import time
from typing import List

from agents.base import BaseAgent
from agents.document_verification_agent import DocumentVerificationAgent
from agents.credit_score_agent import CreditScoreAgent
from agents.income_assessment_agent import IncomeAssessmentAgent
from agents.risk_assessment_agent import RiskAssessmentAgent
from agents.compliance_agent import ComplianceAgent
from core.models import AgentResult, AgentStatus, CustomerApplication, LoanDecision
from core.decision_engine import DecisionEngine
from config.settings import settings


class OrchestratorAgent:
    """
    Master controller that coordinates all sub-agents and
    drives the loan decision pipeline.
    """

    def __init__(self):
        self.agents: List[BaseAgent] = [
            DocumentVerificationAgent(),
            CreditScoreAgent(),
            IncomeAssessmentAgent(),
            RiskAssessmentAgent(),
            ComplianceAgent(),
        ]
        self.decision_engine = DecisionEngine()

    async def process(self, application: CustomerApplication) -> LoanDecision:
        """
        Full pipeline execution:
          1. Fan out to all agents in parallel
          2. Collect results (with timeout handling)
          3. Run Decision Engine
          4. Return LoanDecision
        """
        wall_start = time.perf_counter()

        agent_tasks = [
            asyncio.wait_for(
                agent.process(application),
                timeout=settings.AGENT_TIMEOUT,
            )
            for agent in self.agents
        ]

        raw_results = await asyncio.gather(*agent_tasks, return_exceptions=True)

        agent_results: List[AgentResult] = []
        for i, result in enumerate(raw_results):
            if isinstance(result, asyncio.TimeoutError):
                agent_results.append(self._timeout_result(self.agents[i]))
            elif isinstance(result, Exception):
                agent_results.append(self._exception_result(self.agents[i], result))
            else:
                agent_results.append(result)

        total_latency = int((time.perf_counter() - wall_start) * 1000)
        return self.decision_engine.decide(application, agent_results, total_latency)

    # ── Fallback result builders ───────────────────────────────────────────

    @staticmethod
    def _timeout_result(agent: BaseAgent) -> AgentResult:
        return AgentResult(
            agent_name = agent.name,
            status     = AgentStatus.ERROR,
            score      = 50.0,
            weight     = agent.weight,
            flags      = ["AGENT_TIMEOUT"],
            mcp_server = agent.mcp_url,
            mcp_result = {"error": "Agent exceeded timeout"},
            latency_ms = int(settings.AGENT_TIMEOUT * 1000),
        )

    @staticmethod
    def _exception_result(agent: BaseAgent, exc: Exception) -> AgentResult:
        return AgentResult(
            agent_name = agent.name,
            status     = AgentStatus.ERROR,
            score      = 50.0,
            weight     = agent.weight,
            flags      = ["AGENT_ERROR"],
            mcp_server = agent.mcp_url,
            mcp_result = {"error": str(exc)},
            latency_ms = 0,
        )
