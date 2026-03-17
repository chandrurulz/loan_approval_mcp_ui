"""
api/gateway.py
==============
FastAPI REST Gateway for the Loan Approval System.

Endpoints:
  POST /api/v1/loans/apply    → Submit loan application
  GET  /api/v1/loans/{id}     → Get decision by application ID
  GET  /api/v1/health         → Health check
  GET  /api/v1/config         → View current scoring config

The gateway:
  - Validates the incoming CustomerApplication via Pydantic
  - Generates a unique application_id
  - Calls OrchestratorAgent.process()
  - Returns the LoanDecision as JSON
  - Maintains an in-memory store (swap for Redis/DB in production)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agents.orchestrator import OrchestratorAgent
from core.models import CustomerApplication, LoanDecision
from config.settings import settings


# In-memory decision store (replace with DB in production)
_decision_store: Dict[str, LoanDecision] = {}
_orchestrator: OrchestratorAgent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _orchestrator
    _orchestrator = OrchestratorAgent()
    print(f"✅ Loan Approval API started — MOCK_DATA={settings.MOCK_DATA}")
    yield
    print("🛑 Shutting down...")


app = FastAPI(
    title="Loan Approval — Multi-Agent AI",
    description="Real-time loan approval using 5 AI agents + MCP servers",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ─────────────────────────────────────────────────────────────────

@app.post("/api/v1/loans/apply", response_model=dict, summary="Submit loan application")
async def apply_for_loan(application: CustomerApplication):
    """
    Submit a loan application for real-time AI evaluation.

    Returns a full LoanDecision including:
    - APPROVE / REFER / REJECT verdict
    - Agent-by-agent breakdown
    - Loan terms (if approved)
    - Reason codes
    """
    decision = await _orchestrator.process(application)
    _decision_store[application.application_id] = decision
    return decision.summary()


@app.get("/api/v1/loans/{application_id}", summary="Get loan decision")
async def get_decision(application_id: str):
    """Retrieve a previously made loan decision by application ID."""
    if application_id not in _decision_store:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")
    return _decision_store[application_id].summary()


@app.get("/api/v1/health", summary="Health check")
async def health():
    return {
        "status": "healthy",
        "mock_mode": settings.MOCK_DATA,
        "agents": 5,
        "mcp_servers": 5,
    }


@app.get("/api/v1/config", summary="Scoring configuration")
async def get_config():
    return {
        "approve_threshold":  settings.APPROVE_THRESHOLD,
        "refer_threshold":    settings.REFER_THRESHOLD,
        "agent_timeout_secs": settings.AGENT_TIMEOUT,
        "weights": {
            "credit_score":          settings.WEIGHT_CREDIT,
            "income_assessment":     settings.WEIGHT_INCOME,
            "document_verification": settings.WEIGHT_DOCS,
            "risk_assessment":       settings.WEIGHT_RISK,
            "compliance":            settings.WEIGHT_COMPLIANCE,
        },
        "rate_bands": settings.RATE_BANDS,
        "processing_fee_pct": settings.PROCESSING_FEE_PCT,
    }
