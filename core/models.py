"""
core/models.py
==============
Shared dataclass models — stdlib only (no Pydantic/FastAPI).
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class Decision(str, Enum):
    APPROVE = "APPROVE"
    REFER   = "REFER"
    REJECT  = "REJECT"

class AgentStatus(str, Enum):
    PASS  = "pass"
    FAIL  = "fail"
    ERROR = "error"

class EmploymentType(str, Enum):
    SALARIED      = "salaried"
    SELF_EMPLOYED = "self_employed"
    BUSINESS      = "business"

class LoanPurpose(str, Enum):
    HOME_PURCHASE      = "home_purchase"
    HOME_RENOVATION    = "home_renovation"
    VEHICLE            = "vehicle"
    EDUCATION          = "education"
    MEDICAL            = "medical"
    BUSINESS           = "business"
    PERSONAL           = "personal"
    DEBT_CONSOLIDATION = "debt_consolidation"


@dataclass
class CustomerApplication:
    customer_name:       str
    pan_number:          str
    aadhaar_number:      str
    date_of_birth:       str
    mobile:              str
    email:               str
    loan_amount:         float
    loan_tenure_months:  int
    monthly_income:      float
    employer_name:       str
    residential_address: str
    loan_purpose:        LoanPurpose    = LoanPurpose.PERSONAL
    employment_type:     EmploymentType = EmploymentType.SALARIED
    years_of_employment: float         = 1.0
    city:                str            = ""
    pincode:             str            = ""
    ip_address:          str            = "0.0.0.0"
    device_id:           str            = ""
    application_id: str = field(default_factory=lambda: f"APP-{uuid.uuid4().hex[:8].upper()}")
    session_id:     str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at:     str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class MCPToolCall:
    tool:       str
    params:     Dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    called_at:  str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class MCPToolResult:
    tool:       str
    server:     str
    success:    bool
    data:       Dict[str, Any]
    error:      Optional[str] = None
    latency_ms: int = 0
    mock_mode:  bool = True
    returned_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AgentResult:
    agent_name:  str
    status:      AgentStatus
    score:       float
    weight:      float
    flags:       List[str]      = field(default_factory=list)
    mcp_server:  str            = ""
    mcp_result:  Optional[Dict] = None
    latency_ms:  int            = 0
    processed_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass
class LoanTerms:
    approved_amount:  float
    interest_rate_pa: float
    tenure_months:    int
    emi_amount:       float
    processing_fee:   float
    total_repayable:  float


@dataclass
class LoanDecision:
    application_id:        str
    decision:              Decision
    final_score:           float
    agent_results:         List[AgentResult]
    loan_terms:            Optional[LoanTerms] = None
    reason_codes:          List[str] = field(default_factory=list)
    human_review_required: bool = False
    decided_at:     str = field(default_factory=lambda: datetime.now().isoformat())
    total_latency_ms: int = 0

    def summary(self) -> Dict[str, Any]:
        return {
            "application_id": self.application_id,
            "decision":       self.decision.value,
            "final_score":    round(self.final_score, 2),
            "loan_terms": {
                "approved_amount":  self.loan_terms.approved_amount,
                "interest_rate_pa": self.loan_terms.interest_rate_pa,
                "tenure_months":    self.loan_terms.tenure_months,
                "emi_amount":       self.loan_terms.emi_amount,
                "processing_fee":   self.loan_terms.processing_fee,
                "total_repayable":  self.loan_terms.total_repayable,
            } if self.loan_terms else None,
            "reason_codes":          self.reason_codes,
            "human_review_required": self.human_review_required,
            "decided_at":            self.decided_at,
            "total_latency_ms":      self.total_latency_ms,
            "agent_breakdown": [
                {
                    "agent":    r.agent_name,
                    "score":    r.score,
                    "weight":   r.weight,
                    "weighted": round(r.weighted_score, 2),
                    "status":   r.status.value,
                    "flags":    r.flags,
                    "mcp":      r.mcp_server,
                    "ms":       r.latency_ms,
                }
                for r in self.agent_results
            ],
        }
