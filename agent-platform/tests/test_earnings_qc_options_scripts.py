import datetime
import importlib.machinery
import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "agent-platform" / "scripts" / "earnings-qc-options"


def load_script(name: str):
    path = SCRIPTS / name
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class EarningsQcOptionsGeneratedCodeTests(unittest.TestCase):
    def test_stage2_generated_qc_algorithm_contains_finalizers(self):
        mod = load_script("earnings-qc-options-scan")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_qc_stage2_project(
            project_dir,
            [{"symbol": "OPEN", "report_date": "2026-08-04", "last_year_report_date": "8/05/2025"}],
            datetime.date(2026, 7, 12),
        )
        main = (project_dir / "main.py").read_text()
        self.assertIn("def mark_unprocessed_symbols", main)
        self.assertIn("def historical_runup_pass", main)
        self.assertIn("def emit_and_quit", main)
        self.assertIn("historical_contract_pass_debug_only", main)
        self.assertIn("FORWARD_LIQUIDITY_GREEKS_PASS_REQUIRES_MULTIYEAR_OPTION_PNL", main)

    def test_multiyear_generated_qc_algorithm_contains_exit_policy_and_chunked_json(self):
        mod = load_script("earnings-qc-multiyear-backtest")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_project(
            project_dir,
            [
                {
                    "symbol": "OPEN",
                    "earnings_date": "2026-08-04",
                    "spot": 4.79,
                    "contracts": [{"strike": 6, "ask": 0.25, "required_move_pct": 25, "days_after_earnings": 3}],
                }
            ],
            8,
        )
        main = (project_dir / "main.py").read_text()
        self.assertIn("pre_earnings_no_hold_through", main)
        self.assertIn("multiyear_json_%02d", main)
        self.assertIn("exit_reason", main)


if __name__ == "__main__":
    unittest.main()
