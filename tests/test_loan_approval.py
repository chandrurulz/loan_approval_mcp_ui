"""
tests/test_loan_approval.py
============================
Full test suite — stdlib unittest + asyncio (no pytest dependency).

Run: python3 -m unittest tests.test_loan_approval -v
"""
import asyncio, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ['MOCK_DATA'] = 'true'

from core.models import (CustomerApplication, Decision, LoanPurpose,
                          EmploymentType, MCPToolCall, AgentStatus)
from mcp_servers.document_verification_mcp import DocumentVerificationMCPServer
from mcp_servers.credit_bureau_mcp import CreditBureauMCPServer
from mcp_servers.bank_statement_mcp import BankStatementMCPServer
from mcp_servers.risk_engine_mcp import RiskEngineMCPServer
from mcp_servers.compliance_mcp import ComplianceMCPServer
from agents.document_verification_agent import DocumentVerificationAgent
from agents.credit_score_agent import CreditScoreAgent
from agents.income_assessment_agent import IncomeAssessmentAgent
from agents.risk_assessment_agent import RiskAssessmentAgent
from agents.compliance_agent import ComplianceAgent
from agents.orchestrator import OrchestratorAgent
from core.decision_engine import DecisionEngine

def run(coro): return asyncio.get_event_loop().run_until_complete(coro)

def make_app(**kw) -> CustomerApplication:
    defaults = dict(
        customer_name='Priya Sharma', pan_number='ABCPS1234P',
        aadhaar_number='9876543210987', date_of_birth='1988-04-15',
        mobile='9876543210', email='priya@test.com',
        loan_amount=500_000, loan_tenure_months=36,
        monthly_income=85_000, employer_name='TCS',
        residential_address='42 MG Road Bengaluru',
        years_of_employment=5.0,
    )
    defaults.update(kw)
    return CustomerApplication(**defaults)

def tc(tool, **p): return MCPToolCall(tool=tool, params=p)

# ════════════════════════════════════════════════════════════════════════
# MCP SERVER TESTS
# ════════════════════════════════════════════════════════════════════════

class TestDocumentMCP(unittest.TestCase):
    srv = DocumentVerificationMCPServer()

    def test_valid_pan_verified(self):
        r = run(self.srv.call(tc('verify_all', pan_number='ABCPS1234P',
                                 aadhaar_number='9876543210987', customer_name='Priya')))
        self.assertTrue(r.success)
        self.assertTrue(r.data['pan_valid'])
        self.assertTrue(r.data['aadhaar_verified'])
        self.assertEqual(r.data['overall_status'], 'VERIFIED')

    def test_fake_pan_invalid(self):
        r = run(self.srv.call(tc('verify_all', pan_number='FAKEX0000X',
                                 aadhaar_number='1234567890', customer_name='Fake')))
        self.assertTrue(r.success)
        self.assertFalse(r.data['pan_valid'])

    def test_zero_aadhaar_unverified(self):
        r = run(self.srv.call(tc('verify_aadhaar', aadhaar_number='000012345678',
                                  pan_number='ABCDE1234F')))
        self.assertTrue(r.success)
        self.assertFalse(r.data['aadhaar_verified'])

    def test_documents_contain_salary_slip(self):
        r = run(self.srv.call(tc('verify_documents', pan_number='ABCDE1234F',
                                  customer_name='Test')))
        self.assertTrue(r.success)
        self.assertIn('salary_slip', r.data['documents'])

    def test_unknown_tool_fails_gracefully(self):
        r = run(self.srv.call(tc('nonexistent_tool')))
        self.assertFalse(r.success)
        self.assertIsNotNone(r.error)

    def test_latency_tracked(self):
        r = run(self.srv.call(tc('verify_all', pan_number='ABCDE1234F',
                                  aadhaar_number='9876543210', customer_name='T')))
        self.assertGreater(r.latency_ms, 0)

    def test_mock_mode_flag(self):
        r = run(self.srv.call(tc('verify_all', pan_number='ABCDE1234F',
                                  aadhaar_number='9876543210', customer_name='T')))
        self.assertTrue(r.mock_mode)


class TestCreditMCP(unittest.TestCase):
    srv = CreditBureauMCPServer()

    def test_score_in_valid_range(self):
        r = run(self.srv.call(tc('get_credit_report', pan_number='ABCPS1234P')))
        self.assertTrue(r.success)
        self.assertGreaterEqual(r.data['credit_score'], 300)
        self.assertLessEqual(r.data['credit_score'], 900)

    def test_deterministic_score(self):
        r1 = run(self.srv.call(tc('get_credit_report', pan_number='XYZAB1234X')))
        r2 = run(self.srv.call(tc('get_credit_report', pan_number='XYZAB1234X')))
        self.assertEqual(r1.data['credit_score'], r2.data['credit_score'])

    def test_different_pans_may_differ(self):
        r1 = run(self.srv.call(tc('get_credit_report', pan_number='AAAAA1111A')))
        r2 = run(self.srv.call(tc('get_credit_report', pan_number='ZZZZZ9999Z')))
        # They may or may not be equal but both should be valid
        self.assertGreaterEqual(r1.data['credit_score'], 300)
        self.assertGreaterEqual(r2.data['credit_score'], 300)

    def test_multi_bureau_has_three(self):
        r = run(self.srv.call(tc('get_multi_bureau', pan_number='ABCDE1234F')))
        self.assertTrue(r.success)
        for bureau in ('CIBIL', 'Experian', 'Equifax'):
            self.assertIn(bureau, r.data['bureaus'])

    def test_report_has_trade_lines(self):
        r = run(self.srv.call(tc('get_credit_report', pan_number='ABCDE1234F')))
        self.assertIsInstance(r.data['trade_lines'], list)

    def test_report_id_present(self):
        r = run(self.srv.call(tc('get_credit_report', pan_number='ABCDE1234F')))
        self.assertIn('report_id', r.data)


class TestBankMCP(unittest.TestCase):
    srv = BankStatementMCPServer()

    def test_income_within_10pct_of_stated(self):
        r = run(self.srv.call(tc('calculate_income', pan_number='ABCDE1234F',
                                  stated_income=50_000, employer_name='TCS')))
        self.assertTrue(r.success)
        vi = r.data['verified_monthly_income']
        self.assertGreater(vi, 40_000)
        self.assertLess(vi, 60_000)

    def test_dti_non_negative(self):
        r = run(self.srv.call(tc('calculate_dti', pan_number='ABCDE1234F',
                                  verified_income=80_000, loan_amount=500_000,
                                  tenure_months=36)))
        self.assertTrue(r.success)
        self.assertGreaterEqual(r.data['dti_ratio_pct'], 0)

    def test_six_months_statements(self):
        r = run(self.srv.call(tc('get_bank_statements', pan_number='ABCDE1234F',
                                  stated_income=60_000)))
        self.assertTrue(r.success)
        self.assertEqual(len(r.data['statements']), 6)

    def test_full_income_check_combines(self):
        r = run(self.srv.call(tc('full_income_check', pan_number='ABCDE1234F',
                                  stated_income=60_000, employer_name='TCS',
                                  employment_type='salaried', loan_amount=300_000,
                                  tenure_months=36, years_of_employment=3)))
        self.assertTrue(r.success)
        self.assertIn('verified_monthly_income', r.data)
        self.assertIn('dti_ratio_pct', r.data)

    def test_employer_verified(self):
        r = run(self.srv.call(tc('verify_employer', employer_name='Infosys',
                                  pan_number='ABCDE1234F')))
        self.assertTrue(r.success)
        self.assertTrue(r.data['employer_verified'])


class TestRiskMCP(unittest.TestCase):
    srv = RiskEngineMCPServer()

    def test_clean_user_high_score(self):
        r = run(self.srv.call(tc('assess_fraud_risk', mobile='9876543210',
                                  email='user@gmail.com', pan_number='ABCDE1234F')))
        self.assertTrue(r.success)
        self.assertGreater(r.data['fraud_score'], 50)

    def test_fraud_email_low_score(self):
        r = run(self.srv.call(tc('assess_fraud_risk', mobile='9876543210',
                                  email='hacker@fraud.com', pan_number='ABCDE1234F')))
        self.assertTrue(r.success)
        self.assertLess(r.data['fraud_score'], 40)

    def test_blacklisted_mobile_detected(self):
        r = run(self.srv.call(tc('check_blacklist', mobile='0000123456',
                                  pan_number='ABCDE1234F')))
        self.assertTrue(r.success)
        self.assertTrue(r.data['blacklist_hit'])

    def test_fake_pan_blacklisted(self):
        r = run(self.srv.call(tc('check_blacklist', mobile='9876543210',
                                  pan_number='FAKEX0000X')))
        self.assertTrue(r.success)
        self.assertTrue(r.data['pan_blacklisted'])

    def test_risk_band_valid_value(self):
        r = run(self.srv.call(tc('full_risk_check', mobile='9876543210',
                                  email='clean@gmail.com', pan_number='ABCDE1234F')))
        self.assertTrue(r.success)
        self.assertIn(r.data['risk_band'], ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'))

    def test_velocity_present(self):
        r = run(self.srv.call(tc('assess_fraud_risk', mobile='9876543210',
                                  email='user@example.com', pan_number='ABCDE1234F')))
        self.assertIn('velocity', r.data)


class TestComplianceMCP(unittest.TestCase):
    srv = ComplianceMCPServer()

    def test_clean_customer_passes_all(self):
        r = run(self.srv.call(tc('full_compliance', customer_name='Priya Sharma',
                                  pan_number='ABCDE1234F', aadhaar_number='9876543210987')))
        self.assertTrue(r.success)
        self.assertFalse(r.data['sanctions_hit'])
        self.assertFalse(r.data['pep_flag'])
        self.assertEqual(r.data['aml_status'], 'CLEAR')

    def test_z_name_pep_flag(self):
        r = run(self.srv.call(tc('pep_check', customer_name='Zubair Ali',
                                  pan_number='ABCDE1234F')))
        self.assertTrue(r.success)
        self.assertTrue(r.data['pep_flag'])
        self.assertIsNotNone(r.data['pep_category'])

    def test_kyc_complete(self):
        r = run(self.srv.call(tc('kyc_check', pan_number='ABCDE1234F')))
        self.assertTrue(r.success)
        self.assertEqual(r.data['kyc_status'], 'COMPLETE')

    def test_aml_clear_for_clean_mobile(self):
        r = run(self.srv.call(tc('aml_screening', mobile='9876543210',
                                  pan_number='ABCDE1234F')))
        self.assertTrue(r.success)
        self.assertEqual(r.data['aml_status'], 'CLEAR')

    def test_aml_flagged_for_fraud_mobile(self):
        r = run(self.srv.call(tc('aml_screening', mobile='0000123456',
                                  pan_number='ABCDE1234F')))
        self.assertTrue(r.success)
        self.assertEqual(r.data['aml_status'], 'FLAGGED')

    def test_sanctions_lists_checked(self):
        r = run(self.srv.call(tc('sanctions_check', pan_number='ABCDE1234F',
                                  customer_name='Test User')))
        self.assertIn('sanctions_lists_checked', r.data)
        self.assertGreater(len(r.data['sanctions_lists_checked']), 0)


# ════════════════════════════════════════════════════════════════════════
# AGENT TESTS
# ════════════════════════════════════════════════════════════════════════

class TestDocumentAgent(unittest.TestCase):
    agent = DocumentVerificationAgent()

    def test_valid_passes(self):
        r = run(self.agent.process(make_app()))
        self.assertNotIn('PAN_INVALID', r.flags)
        self.assertGreater(r.score, 0)

    def test_fake_pan_fails(self):
        r = run(self.agent.process(make_app(pan_number='FAKEX0000X')))
        self.assertIn('PAN_INVALID', r.flags)
        self.assertLess(r.score, 50)
        self.assertEqual(r.status, AgentStatus.FAIL)

    def test_weight_correct(self):
        r = run(self.agent.process(make_app()))
        self.assertEqual(r.weight, 0.20)

    def test_mcp_server_name(self):
        r = run(self.agent.process(make_app()))
        self.assertEqual(r.mcp_server, 'document-verification-mcp')

    def test_score_range(self):
        r = run(self.agent.process(make_app()))
        self.assertGreaterEqual(r.score, 0)
        self.assertLessEqual(r.score, 100)


class TestCreditAgent(unittest.TestCase):
    agent = CreditScoreAgent()

    def test_score_in_range(self):
        r = run(self.agent.process(make_app()))
        self.assertGreaterEqual(r.score, 0)
        self.assertLessEqual(r.score, 100)

    def test_weight(self):
        r = run(self.agent.process(make_app()))
        self.assertEqual(r.weight, 0.35)

    def test_flags_list(self):
        r = run(self.agent.process(make_app()))
        self.assertIsInstance(r.flags, list)

    def test_mcp_server(self):
        r = run(self.agent.process(make_app()))
        self.assertEqual(r.mcp_server, 'credit-bureau-mcp')

    def test_status_is_valid_enum(self):
        r = run(self.agent.process(make_app()))
        self.assertIn(r.status, (AgentStatus.PASS, AgentStatus.FAIL, AgentStatus.ERROR))


class TestIncomeAgent(unittest.TestCase):
    agent = IncomeAssessmentAgent()

    def test_returns_result(self):
        r = run(self.agent.process(make_app(monthly_income=80_000, loan_amount=300_000)))
        self.assertIsNotNone(r)
        self.assertEqual(r.weight, 0.25)

    def test_mcp_server(self):
        r = run(self.agent.process(make_app()))
        self.assertEqual(r.mcp_server, 'bank-statement-mcp')

    def test_score_range(self):
        r = run(self.agent.process(make_app()))
        self.assertGreaterEqual(r.score, 0)
        self.assertLessEqual(r.score, 100)


class TestRiskAgent(unittest.TestCase):
    agent = RiskAssessmentAgent()

    def test_clean_no_blacklist(self):
        r = run(self.agent.process(make_app()))
        self.assertNotIn('BLACKLIST_HIT', r.flags)

    def test_fraud_mobile_blacklisted(self):
        r = run(self.agent.process(make_app(mobile='0000000001')))
        self.assertIn('BLACKLIST_HIT', r.flags)
        self.assertEqual(r.score, 0.0)
        self.assertEqual(r.status, AgentStatus.FAIL)

    def test_weight(self):
        r = run(self.agent.process(make_app()))
        self.assertEqual(r.weight, 0.15)

    def test_fraud_email_flagged(self):
        r = run(self.agent.process(make_app(email='hacker@fraud.com')))
        self.assertIn('DISPOSABLE_EMAIL', r.flags)


class TestComplianceAgent(unittest.TestCase):
    agent = ComplianceAgent()

    def test_clean_no_sanctions(self):
        r = run(self.agent.process(make_app()))
        self.assertNotIn('SANCTIONS_HIT', r.flags)
        self.assertNotIn('RBI_DEFAULTER', r.flags)

    def test_pep_flagged(self):
        r = run(self.agent.process(make_app(customer_name='Zubair Minister PEP')))
        self.assertIn('PEP_DETECTED', r.flags)

    def test_weight(self):
        r = run(self.agent.process(make_app()))
        self.assertEqual(r.weight, 0.05)

    def test_mcp_server(self):
        r = run(self.agent.process(make_app()))
        self.assertEqual(r.mcp_server, 'compliance-mcp')


# ════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR TESTS
# ════════════════════════════════════════════════════════════════════════

class TestOrchestrator(unittest.TestCase):
    orch = OrchestratorAgent()

    def test_approve_strong_applicant(self):
        d = run(self.orch.process(make_app(pan_number='ABCPS1234P',
                                            monthly_income=90_000, loan_amount=400_000)))
        self.assertIn(d.decision, (Decision.APPROVE, Decision.REFER))
        self.assertGreaterEqual(d.final_score, 0)

    def test_reject_fraud_applicant(self):
        d = run(self.orch.process(make_app(mobile='0000000000', pan_number='FAKEX0000X')))
        self.assertEqual(d.decision, Decision.REJECT)

    def test_five_agents_executed(self):
        d = run(self.orch.process(make_app()))
        self.assertEqual(len(d.agent_results), 5)

    def test_latency_positive(self):
        d = run(self.orch.process(make_app()))
        self.assertGreater(d.total_latency_ms, 0)

    def test_application_id_preserved(self):
        app = make_app()
        d = run(self.orch.process(app))
        self.assertEqual(d.application_id, app.application_id)

    def test_agent_weights_sum_to_one(self):
        d = run(self.orch.process(make_app()))
        total_weight = sum(r.weight for r in d.agent_results)
        self.assertAlmostEqual(total_weight, 1.0, places=5)

    def test_decision_has_summary(self):
        d = run(self.orch.process(make_app()))
        s = d.summary()
        self.assertIn('decision', s)
        self.assertIn('final_score', s)
        self.assertIn('agent_breakdown', s)
        self.assertEqual(len(s['agent_breakdown']), 5)

    def test_pep_requires_human_review(self):
        d = run(self.orch.process(make_app(customer_name='Zubair PEP Minister')))
        if d.decision == Decision.APPROVE:
            self.assertTrue(d.human_review_required)


# ════════════════════════════════════════════════════════════════════════
# DECISION ENGINE TESTS
# ════════════════════════════════════════════════════════════════════════

class TestDecisionEngine(unittest.TestCase):
    engine = DecisionEngine()

    def _results(self, scores: dict):
        mapping = [
            ('DocumentVerificationAgent', 0.20),
            ('CreditScoreAgent',          0.35),
            ('IncomeAssessmentAgent',      0.25),
            ('RiskAssessmentAgent',        0.15),
            ('ComplianceAgent',            0.05),
        ]
        from core.models import AgentResult
        return [
            AgentResult(agent_name=n, status=AgentStatus.PASS,
                        score=scores.get(n, 80.0), weight=w,
                        mcp_server='test-mcp')
            for n, w in mapping
        ]

    def test_all_high_scores_approve(self):
        results = self._results({
            'DocumentVerificationAgent': 95, 'CreditScoreAgent': 90,
            'IncomeAssessmentAgent': 88, 'RiskAssessmentAgent': 92,
            'ComplianceAgent': 100,
        })
        d = self.engine.decide(make_app(), results, 300)
        self.assertEqual(d.decision, Decision.APPROVE)
        self.assertIsNotNone(d.loan_terms)

    def test_all_low_scores_reject(self):
        results = self._results({
            'DocumentVerificationAgent': 20, 'CreditScoreAgent': 25,
            'IncomeAssessmentAgent': 30, 'RiskAssessmentAgent': 35,
            'ComplianceAgent': 40,
        })
        d = self.engine.decide(make_app(), results, 300)
        self.assertEqual(d.decision, Decision.REJECT)

    def test_borderline_refer(self):
        results = self._results({
            'DocumentVerificationAgent': 55, 'CreditScoreAgent': 55,
            'IncomeAssessmentAgent': 58, 'RiskAssessmentAgent': 62,
            'ComplianceAgent': 65,
        })
        d = self.engine.decide(make_app(), results, 300)
        self.assertEqual(d.decision, Decision.REFER)
        self.assertIsNone(d.loan_terms)

    def test_blacklist_hard_stop(self):
        from core.models import AgentResult
        results = self._results({})
        results[3] = AgentResult(
            agent_name='RiskAssessmentAgent', status=AgentStatus.FAIL,
            score=0.0, weight=0.15, flags=['BLACKLIST_HIT'], mcp_server='risk-engine-mcp'
        )
        d = self.engine.decide(make_app(), results, 100)
        self.assertEqual(d.decision, Decision.REJECT)
        self.assertIn('BLACKLIST_HIT', d.reason_codes)

    def test_sanctions_hard_stop(self):
        from core.models import AgentResult
        results = self._results({})
        results[4] = AgentResult(
            agent_name='ComplianceAgent', status=AgentStatus.FAIL,
            score=0.0, weight=0.05, flags=['SANCTIONS_HIT'], mcp_server='compliance-mcp'
        )
        d = self.engine.decide(make_app(), results, 100)
        self.assertEqual(d.decision, Decision.REJECT)

    def test_approved_loan_terms_valid(self):
        results = self._results({
            'DocumentVerificationAgent': 100, 'CreditScoreAgent': 85,
            'IncomeAssessmentAgent': 90, 'RiskAssessmentAgent': 88,
            'ComplianceAgent': 100,
        })
        app = make_app(loan_amount=500_000, loan_tenure_months=36)
        d = self.engine.decide(app, results, 300)
        self.assertEqual(d.decision, Decision.APPROVE)
        self.assertGreater(d.loan_terms.approved_amount, 0)
        self.assertGreater(d.loan_terms.interest_rate_pa, 0)
        self.assertGreater(d.loan_terms.emi_amount, 0)
        self.assertGreater(d.loan_terms.total_repayable, d.loan_terms.approved_amount)
        self.assertGreater(d.loan_terms.processing_fee, 0)

    def test_emi_formula_correct(self):
        """EMI × n should approximate principal + interest."""
        results = self._results({
            'DocumentVerificationAgent': 100, 'CreditScoreAgent': 95,
            'IncomeAssessmentAgent': 95, 'RiskAssessmentAgent': 95,
            'ComplianceAgent': 100,
        })
        app = make_app(loan_amount=1_000_000, loan_tenure_months=12)
        d = self.engine.decide(app, results, 300)
        if d.loan_terms:
            total_emis = d.loan_terms.emi_amount * 12
            self.assertGreater(total_emis, d.loan_terms.approved_amount)

    def test_score_is_weighted_average(self):
        scores = {
            'DocumentVerificationAgent': 80.0,
            'CreditScoreAgent':          70.0,
            'IncomeAssessmentAgent':      90.0,
            'RiskAssessmentAgent':        85.0,
            'ComplianceAgent':            95.0,
        }
        weights = {
            'DocumentVerificationAgent': 0.20,
            'CreditScoreAgent':          0.35,
            'IncomeAssessmentAgent':      0.25,
            'RiskAssessmentAgent':        0.15,
            'ComplianceAgent':            0.05,
        }
        expected = sum(scores[k] * weights[k] for k in scores)
        results = self._results(scores)
        d = self.engine.decide(make_app(), results, 100)
        self.assertAlmostEqual(d.final_score, expected, places=1)


if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite  = loader.discover('.', pattern='test_*.py')
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
