# 🏦 Real-Time Loan Approval — Multi-Agent AI Orchestration

End-to-end Python system using multi-agent AI orchestration with MCP (Model Context Protocol) servers.

## Architecture

```
Customer Application (HTTP POST /api/v1/loans/apply)
        │
        ▼
   FastAPI Gateway  (api/gateway.py)
        │
        ▼
 Orchestrator Agent  (agents/orchestrator.py)
        │
        ├──── async fan-out to 5 agents in parallel ───────────────┐
        │                                                           │
   [Doc Agent] [Credit Agent] [Income Agent] [Risk Agent] [Compliance Agent]
        │           │              │              │               │
   doc-mcp    credit-mcp      bank-mcp       risk-mcp      compliance-mcp
        │           │              │              │               │
   DigiLocker   CIBIL/         Account        Fraud/          RBI/FATF/
   UIDAI/NSDL  Experian/       Aggregator     Risk Engine     OFAC/WorldCheck
               Equifax
        └───────────────────────────────────────────────────────────┘
                                      │
                               Decision Engine
                            (Weighted Score → Verdict)
                                      │
                          Approve / Refer / Reject
```

## Scoring Weights

| Agent                | Weight | MCP Server                  |
|----------------------|--------|-----------------------------|
| Credit Score         |   35%  | credit-bureau-mcp           |
| Income Assessment    |   25%  | bank-statement-mcp          |
| Document Verification|   20%  | document-verification-mcp   |
| Risk Assessment      |   15%  | risk-engine-mcp             |
| Compliance           |    5%  | compliance-mcp              |

## Quick Start

```bash
pip install -r requirements.txt
MOCK_DATA=true python main.py
```
