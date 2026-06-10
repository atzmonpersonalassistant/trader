import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "research_report", ROOT / "quantconnect-poc" / "reports" / "research_report.py"
)
research_report = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = research_report
spec.loader.exec_module(research_report)


class QuantConnectPocReportTests(unittest.TestCase):
    def test_rejects_live_trading_config(self):
        with self.assertRaises(ValueError):
            research_report.validate_config({"live_trading": True})

    def test_rejects_excessive_risk(self):
        with self.assertRaises(ValueError):
            research_report.validate_config({"max_risk_fraction": 0.05})

    def test_discards_too_few_trades(self):
        verdict = research_report.evaluate({"trade_count": 12, "sharpe": 1.2, "max_drawdown_pct": 5})
        self.assertEqual(verdict.verdict, "discard_or_refine")
        self.assertTrue(any("too few trades" in r for r in verdict.reasons))

    def test_discards_zero_profit_factor_when_present(self):
        verdict = research_report.evaluate(
            {"trade_count": 40, "sharpe": 1.2, "max_drawdown_pct": 5, "profit_factor": 0}
        )
        self.assertEqual(verdict.verdict, "discard_or_refine")
        self.assertTrue(any("profit factor" in r for r in verdict.reasons))

    def test_renders_report_without_secret_values(self):
        report = research_report.render_report(
            {
                "underlying": "SPY",
                "strategy": "bear_call",
                "api_token": "SECRET",
                "api_key": "KEY",
                "password": "PASSWORD",
                "authorization": "Bearer abc",
            },
            {"trade_count": 40, "sharpe": 0.8, "max_drawdown_pct": 8, "profit_factor": 1.2},
        )
        self.assertIn("paper_test_candidate", report)
        self.assertNotIn("SECRET", report)
        self.assertNotIn("KEY", report)
        self.assertNotIn("PASSWORD", report)
        self.assertNotIn("Bearer abc", report)


if __name__ == "__main__":
    unittest.main()
