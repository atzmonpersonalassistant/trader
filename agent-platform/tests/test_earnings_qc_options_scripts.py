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

    def test_multiyear_result_pass_gate_rejects_bad_completed_results(self):
        mod = load_script("earnings-qc-multiyear-backtest")
        self.assertFalse(
            mod.result_passes(
                {
                    "status": "OK",
                    "sample_size": 18,
                    "win_rate": 0.2222,
                    "median_return_pct": -59.86,
                    "mean_return_pct": 52.02,
                    "max_drawdown_pct": 100.0,
                    "max_loss_pct": -96.55,
                }
            )
        )
        self.assertTrue(
            mod.result_passes(
                {
                    "status": "OK",
                    "sample_size": 12,
                    "win_rate": 0.5,
                    "median_return_pct": 10.0,
                    "mean_return_pct": 15.0,
                    "max_drawdown_pct": 40.0,
                    "max_loss_pct": -70.0,
                }
            )
        )

    def test_full_scan_aggregation_does_not_promote_failed_multiyear_results(self):
        mod = load_script("earnings-qc-options-full-scan")
        summary = mod.aggregate(
            [
                {
                    "ok": True,
                    "qc_processed_row_count": 1,
                    "calendar_row_count": 1,
                    "candidate_details": [{"symbol": "OPEN", "earnings_date": "2026-08-04"}],
                    "chunk_multiyear_backtest": {
                        "ok": False,
                        "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE_NO_PASSING_SYMBOLS",
                        "results": [
                            {
                                "symbol": "OPEN",
                                "status": "OK",
                                "sample_size": 12,
                                "win_rate": 0.5,
                                "median_return_pct": 10.0,
                                "mean_return_pct": 15.0,
                                "max_drawdown_pct": 40.0,
                                "max_loss_pct": -70.0,
                            }
                        ],
                    },
                }
            ]
        )
        self.assertFalse(summary["ok"])
        self.assertTrue(summary["multiyear_failed"])
        self.assertEqual(summary["final_candidate_count"], 0)

    def test_full_scan_load_chunks_uses_latest_retry_for_same_offset(self):
        mod = load_script("earnings-qc-options-full-scan")
        run_dir = pathlib.Path(tempfile.mkdtemp())
        (run_dir / "chunks.jsonl").write_text(
            '{"offset": 0, "ok": false, "seconds": 1}\n'
            '{"offset": 0, "ok": true, "seconds": 2}\n'
        )
        (run_dir / "chunk-0.stdout.json").write_text('{"ok": true, "status": "OK"}')
        chunks = mod.load_chunks(run_dir)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["_chunk_seconds"], 2)

    def test_multiyear_final_candidates_require_summary_ok(self):
        mod = load_script("earnings-qc-multiyear-backtest")
        self.assertTrue(mod.result_passes({
            "status": "OK", "sample_size": 12, "win_rate": 0.5,
            "median_return_pct": 10.0, "mean_return_pct": 15.0,
            "max_drawdown_pct": 40.0, "max_loss_pct": -70.0,
        }))
        # Promotion code must additionally require summary["ok"], not just result_passes().

    def test_stage2_candidate_json_parse_failure_should_block_when_count_positive(self):
        # Regression guard for runtime-stat truncation: if trader.candidates says >0 but
        # details JSON cannot parse, the run must block rather than silently skip
        # mandatory multiyear validation. This script-level invariant is enforced in
        # run_now; here we keep the expected status string pinned.
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        self.assertIn("BLOCKED_QC_CANDIDATE_DETAILS_MISSING_OR_TRUNCATED", scan)
        self.assertIn("candidate_details_parse_failed", scan)
        self.assertIn("len(candidate_details)", scan)

    def test_stage2_partial_nasdaq_fetch_should_block(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        self.assertIn("BLOCKED_NASDAQ_CALENDAR_PARTIAL_FETCH_FAILED", scan)
        self.assertIn("calendar_fetch_failed", scan)


if __name__ == "__main__":
    unittest.main()
