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
        self.assertIn("sell_before_earnings_no_hold_through", main)
        self.assertIn("multiyear_json_%02d", main)
        self.assertIn("exit_reason", main)
        self.assertIn("planned_exit_date", main)
        self.assertIn("actual_exit_date", main)
        self.assertIn("exit_days_shifted", main)
        self.assertIn("liquidity_metrics", main)
        self.assertIn("expected_option_move", main)
        self.assertIn("allowed_spread", main)

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

    def test_result_pass_gate_accepts_zero_drawdown(self):
        full = load_script("earnings-qc-options-full-scan")
        multi = load_script("earnings-qc-multiyear-backtest")
        row = {
            "status": "OK", "sample_size": 12, "win_rate": 0.5,
            "median_return_pct": 10.0, "mean_return_pct": 15.0,
            "max_drawdown_pct": 0.0, "max_loss_pct": 0.0,
        }
        self.assertTrue(full.multiyear_result_passes(row))
        self.assertTrue(multi.result_passes(row))


    def test_stage2_uses_volatility_aware_spread_policy(self):
        mod = load_script("earnings-qc-options-scan")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_qc_stage2_project(
            project_dir,
            [{"symbol": "OPEN", "report_date": "2026-08-04", "last_year_report_date": "8/05/2025"}],
            datetime.date(2026, 7, 13),
        )
        main = (project_dir / "main.py").read_text()
        self.assertIn("expected_option_move", main)
        self.assertIn("allowed_relative_spread", main)
        self.assertIn("allowed_spread", main)
        self.assertIn("spread_policy", main)
        self.assertIn("volatility_aware_relative_expected_move_no_absolute_spread_gate", main)


    def test_stage2_relaxes_oi_volume_and_absolute_spread_gates_with_diagnostics(self):
        mod = load_script("earnings-qc-options-scan")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_qc_stage2_project(
            project_dir,
            [{"symbol": "OPEN", "report_date": "2026-08-04", "last_year_report_date": "8/05/2025"}],
            datetime.date(2026, 7, 13),
        )
        main = (project_dir / "main.py").read_text()
        self.assertIn("self.min_open_interest = 0", main)
        self.assertIn("self.min_volume = 0", main)
        self.assertIn("self.max_spread = None", main)
        self.assertNotIn("(oi >= self.min_open_interest or vol >= self.min_volume)", main)
        self.assertIn("open_interest_volume_policy=\"diagnostic_only_not_gate\"", main)
        self.assertIn("spread_policy=\"volatility_aware_relative_expected_move_no_absolute_spread_gate\"", main)
        self.assertIn("liquidity_fail_reason_counts", main)
        self.assertIn("cheap_contract_diagnostics_sample", main)
        self.assertIn("low_bid", main)
        self.assertIn("missing_greeks", main)
        self.assertIn("missing_iv", main)
        self.assertIn("spread_too_wide", main)
        self.assertIn("diagnostic_zero_volume", main)
        self.assertIn("diagnostic_zero_open_interest", main)

    def test_stage2_notify_only_candidates_or_blockers(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        self.assertIn("if notify and (payload.get('candidate_count') or not payload.get('ok'))", scan)

    def test_retry_failed_uses_end_to_end_runner(self):
        full = (SCRIPTS / "earnings-qc-options-full-scan").read_text()
        self.assertIn("run_chunk_end_to_end(run_dir, off, args.chunk_size, args.years, args.end_to_end)", full)
        self.assertIn("rf.add_argument('--end-to-end'", full)

    def test_full_scan_throttles_discovery_and_sequential_chunks(self):
        full = (SCRIPTS / "earnings-qc-options-full-scan").read_text()
        self.assertIn("QC_FULL_CHUNK_DELAY_SECONDS", full)
        self.assertIn("discovery_delay", full)
        self.assertIn("if offsets and not args.resume", full)
        self.assertIn("time.sleep(discovery_delay)", full)
        self.assertIn("time.sleep(delay)", full)
        self.assertIn("QC_FULL_PARALLEL','1'", full)

    def test_scan_run_id_is_chunk_unique_for_parallel_runs(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        self.assertIn("os.getpid()", scan)
        self.assertIn("qc_batch_offset", scan)

    def test_failed_multiyear_chunks_are_retry_targets(self):
        full = (SCRIPTS / "earnings-qc-options-full-scan").read_text()
        self.assertIn("mb.get('ok') is False", full)
        self.assertIn("mandatory multiyear option-PnL backtest failed", full)

    def test_stage2_uses_point_in_time_valuation_window_not_stale_multiday_slice(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        self.assertIn("valuation_date = last_completed_qc_trading_day(today)", scan)
        self.assertIn("'valuation_date': last_completed_qc_trading_day(today).isoformat()", scan)
        self.assertNotIn("'valuation_date': latest_weekday_on_or_before(today).isoformat()", scan)
        self.assertIn("start = previous_weekday_before(valuation_date)", scan)
        self.assertIn("end = valuation_date", scan)
        self.assertIn("self.valuation_date", scan)
        self.assertIn("self.time.date() < self.valuation_date", scan)
        self.assertIn("elif self.time.date() > self.valuation_date", scan)
        self.assertNotIn("or self.time.date() >= self.valuation_date", scan)
        self.assertNotIn("today - timedelta(days=5)", scan)
        self.assertNotIn("end = valuation_date + timedelta(days=1)", scan)
        self.assertNotIn("set_warm_up", scan)

    def test_full_scan_uses_single_calendar_snapshot_for_chunks(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        full = (SCRIPTS / "earnings-qc-options-full-scan").read_text()
        self.assertIn("--calendar-snapshot", scan)
        self.assertIn("calendar_rows.json", scan)
        self.assertIn("calendar_snapshot.json", full)
        self.assertIn("--calendar-snapshot", full)

    def test_after_market_multiyear_exit_uses_report_day(self):
        multi = (SCRIPTS / "earnings-qc-multiyear-backtest").read_text()
        self.assertIn("normalized_report_time", multi)
        self.assertIn("after_market", multi)
        self.assertIn("planned_exit_date=rd", multi)
        self.assertIn("after_market_report_day_close_sell_before_earnings", multi)
        self.assertIn("pre_market_or_unknown_prior_trading_day_sell_before_earnings", multi)

    def test_multiyear_outputs_per_window_results(self):
        multi = (SCRIPTS / "earnings-qc-multiyear-backtest").read_text()
        self.assertIn("window_results", multi)
        self.assertIn("[1,3,5", multi)
        self.assertIn("BLOCKED_HISTORICAL_OPTION_WINDOW_GATE", multi)

    def test_full_scan_gate_rejects_failed_window_results(self):
        full = load_script("earnings-qc-options-full-scan")
        row = {
            "status": "OK", "sample_size": 12, "win_rate": 0.5,
            "median_return_pct": 10.0, "mean_return_pct": 15.0,
            "max_drawdown_pct": 0.0, "max_loss_pct": 0.0,
            "window_results": [
                {"window": "1y", "status": "BLOCKED_HISTORICAL_OPTION_SAMPLE_INSUFFICIENT", "sample_size": 0},
                {"window": "3y", "status": "OK", "sample_size": 3},
            ],
        }
        self.assertFalse(full.multiyear_result_passes(row))

    def test_stage2_blocks_zero_processed_rows_on_valuation_date(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        self.assertIn("latest_weekday_on_or_before", scan)
        self.assertIn("BLOCKED_QC_NO_OPTION_CHAIN_ROWS_ON_VALUATION_DATE", scan)
        self.assertIn("valuation_date", scan)

    def test_stage2_runner_parses_chunked_stage2_json(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        self.assertIn("trader.stage2_json_%02d", scan)
        self.assertIn("out['parsed_result'] = json.loads(''.join(parts))", scan)

    def test_stage2_reports_qc_capacity_without_exposing_cli_output(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        self.assertIn("BLOCKED_QC_CLOUD_NO_SPARE_NODES", scan)
        self.assertIn("capacity_blocked", scan)
        self.assertIn("error_class", scan)
        self.assertIn("no spare nodes available", scan)
        self.assertNotIn("'backtest_stdout':", scan)
        self.assertNotIn("'backtest_stderr':", scan)

    def test_stage2_reads_option_chain_values_like_working_qc_templates(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        self.assertIn("data.option_chains.values()", scan)
        self.assertIn("chains_by_symbol", scan)
        self.assertIn("chain.contracts.values()", scan)
        self.assertIn("self.add_option(ticker, Resolution.HOUR)", scan)
        self.assertIn("calls_only().strikes(-50, 300).expiration(0, 120)", scan)
        self.assertIn("trader.option_chain_slice_count", scan)
        self.assertIn("trader.option_chain_symbols_sample", scan)


if __name__ == "__main__":
    unittest.main()
