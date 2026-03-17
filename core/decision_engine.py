"""
core/decision_engine.py
========================
Decision Engine — the final arbiter of the loan approval pipeline.

Aggregates weighted scores from all agents and applies:
  1. Hard-stop flag check   → instant REJECT if any critical flag present
  2. Weighted composite scoring → APPROVE / REFER / REJECT based on thresholds
  3. Loan term calculation  → amount, rate, tenure, EMI for approved loans
  4. Reason code generation → human-readable codes for every decision

Thresholds (configurable via settings.py):
  >= 70  →  APPROVE
  50–69  →  REFER  (route to human underwriter)
  < 50   →  REJECT

Hard-stop flags (instant REJECT regardless of score):
  BLACKLIST_HIT · SANCTIONS_HIT · RBI_DEFAULTER · PAN_INVALID · DTI_CRITICAL

EMI formula (reducing balance):
  EMI = P × r × (1+r)^n / ((1+r)^n - 1)
  where r = monthly_rate, n = tenure_months
"""

from __future__ import annotations

import math
from typing import List, Optional

from core.models import AgentResult, CustomerApplication, Decision, LoanDecision, LoanTerms
from config.settings import settings


class DecisionEngine:
    """Aggregates all agent results into a final loan decision."""

    # Flags that immediately trigger REJECT regardless of overall score
    HARD_STOP_FLAGS = frozenset({
        "BLACKLIST_HIT",
        "SANCTIONS_HIT",
        "RBI_DEFAULTER",
        "PAN_INVALID",
        "DTI_CRITICAL",
        "FRAUD_RISK_CRITICAL",
    })

    # Flags that require human review even if score qualifies for APPROVE
    HUMAN_REVIEW_FLAGS = frozenset({
        "PEP_DETECTED",
        "AML_FLAGGED",
        "DOCUMENT_TAMPERED",
        "INCOME_MISMATCH",
        "SYNTHETIC_IDENTITY_SUSPECT",
        "ADVERSE_MEDIA",
    })

    def decide(
        self,
        application: CustomerApplication,
        agent_results: List[AgentResult],
        total_latency_ms: int,
    ) -> LoanDecision:
        all_flags = [f for r in agent_results for f in r.flags]

        # ── Hard Stop Check ────────────────────────────────────────────────
        hard_stops = [f for f in all_flags if f in self.HARD_STOP_FLAGS]
        if hard_stops:
            return LoanDecision(
                application_id    = application.application_id,
                decision          = Decision.REJECT,
                final_score       = 0.0,
                agent_results     = agent_results,
                reason_codes      = hard_stops,
                human_review_required = False,
                total_latency_ms  = total_latency_ms,
            )

        # ── Weighted Score ─────────────────────────────────────────────────
        final_score = sum(r.score * r.weight for r in agent_results)
        reason_codes = sorted(set(all_flags))
        human_review = any(f in self.HUMAN_REVIEW_FLAGS for f in all_flags)

        # ── Decision ───────────────────────────────────────────────────────
        if final_score >= settings.APPROVE_THRESHOLD:
            decision   = Decision.APPROVE
            loan_terms = self._calculate_terms(application, final_score)
            if human_review:
                reason_codes.append("HUMAN_REVIEW_RECOMMENDED")
        elif final_score >= settings.REFER_THRESHOLD:
            decision   = Decision.REFER
            loan_terms = None
            reason_codes.append("UNDERWRITER_REVIEW_REQUIRED")
            human_review = True
        else:
            decision   = Decision.REJECT
            loan_terms = None

        return LoanDecision(
            application_id        = application.application_id,
            decision              = decision,
            final_score           = round(final_score, 2),
            agent_results         = agent_results,
            loan_terms            = loan_terms,
            reason_codes          = reason_codes,
            human_review_required = human_review,
            total_latency_ms      = total_latency_ms,
        )

    # ── Loan Term Calculation ──────────────────────────────────────────────

    def _calculate_terms(self, app: CustomerApplication, score: float) -> LoanTerms:
        # Amount: reduce for borderline scores
        amount_multiplier = 1.0 if score >= 85 else (0.9 if score >= 75 else 0.75)
        approved_amount = round(app.loan_amount * amount_multiplier, -3)   # round to nearest 1000

        # Rate from bands
        rate_pa = self._get_rate(score)

        # EMI (reducing balance)
        emi = self._calc_emi(approved_amount, rate_pa / 12 / 100, app.loan_tenure_months)

        # Processing fee
        processing_fee = round(approved_amount * settings.PROCESSING_FEE_PCT, 2)

        total_repayable = round(emi * app.loan_tenure_months + processing_fee, 2)

        return LoanTerms(
            approved_amount  = approved_amount,
            interest_rate_pa = rate_pa,
            tenure_months    = app.loan_tenure_months,
            emi_amount       = emi,
            processing_fee   = processing_fee,
            total_repayable  = total_repayable,
        )

    def _get_rate(self, score: float) -> float:
        for threshold, rate in settings.RATE_BANDS:
            if score >= threshold:
                return rate
        return 13.5   # fallback for very low scores that still pass

    @staticmethod
    def _calc_emi(principal: float, monthly_rate: float, n: int) -> float:
        if monthly_rate == 0:
            return round(principal / n, 2)
        emi = principal * monthly_rate * (1 + monthly_rate) ** n / ((1 + monthly_rate) ** n - 1)
        return round(emi, 2)
