import contextlib
import argparse
import datetime
import io
import importlib.machinery
import importlib.util
import json
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

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


    def test_single_public_research_cli_uses_internal_libexec_stages(self):
        cli = (SCRIPTS / "earnings-qc-research").read_text()
        self.assertIn("/agents/research/libexec/earnings-qc-options/earnings-qc-options-scan", cli)
        self.assertIn("/agents/research/libexec/earnings-qc-options/earnings-qc-multiyear-backtest", cli)
        self.assertNotIn("SCANNER = pathlib.Path('/agents/research/bin/earnings-qc-options-scan')", cli)
        self.assertNotIn("MULTIYEAR = pathlib.Path('/agents/research/bin/earnings-qc-multiyear-backtest')", cli)

    def test_research_cli_exposes_llm_research_commands(self):
        mod = load_script("earnings-qc-research")
        parser = mod.build_parser()
        commands = parser._subparsers._group_actions[0].choices
        for name in ["run", "status", "history", "insights", "historical", "decision", "cleanup"]:
            self.assertIn(name, commands)
        args = parser.parse_args(["run", "--campaign", "test", "--years", "1", "--from-stage", "historical_option_pnl"])
        self.assertEqual(args.campaign, "test")
        self.assertEqual(args.years, 1)
        self.assertEqual(args.from_stage, "historical_option_pnl")

    def test_research_cli_has_postgres_persistence_schema(self):
        cli = (SCRIPTS / "earnings-qc-research").read_text()
        for table in ["research_campaigns", "research_runs", "research_stages", "stage_artifacts", "candidate_dossiers", "research_decisions", "cleanup_runs"]:
            self.assertIn(table, cli)
        self.assertIn("historical_option_pnl_years_", cli)
        self.assertIn("derive_insights", cli)

    def test_research_schema_identifier_is_sanitized(self):
        mod = load_script("earnings-qc-research")
        self.assertEqual(mod.safe_identifier("earnings_cache", "fallback"), "earnings_cache")
        self.assertEqual(mod.safe_identifier("bad;drop schema public", "fallback"), "fallback")
        self.assertEqual(mod.safe_identifier("1bad", "fallback"), "fallback")

    def test_candidate_persistence_keeps_forward_leads_when_final_exists(self):
        mod = load_script("earnings-qc-research")
        calls = []
        summary = {
            "final_candidates": [{"symbol": "AAA", "earnings_date": "2026-08-01"}],
            "forward_candidates": [
                {"symbol": "AAA", "earnings_date": "2026-08-01"},
                {"symbol": "BBB", "earnings_date": "2026-08-02"},
            ],
            "multiyear_backtest": {"results": [{"symbol": "AAA", "sample_size": 10, "win_rate": 0.6}]},
        }
        with mock.patch.object(mod, "ensure_research_db", return_value=True), \
             mock.patch.object(mod, "db_exec", side_effect=lambda sql: calls.append(sql) or ""):
            mod.persist_candidates("camp", "run", summary)
        joined = "\n".join(calls)
        self.assertIn("AAA", joined)
        self.assertIn("BBB", joined)
        self.assertIn("sample_size", joined)
        self.assertIn("historical_pnl_json=EXCLUDED.historical_pnl_json", joined)
        self.assertEqual(len(calls), 2)

    def test_run_from_historical_stage_delegates_before_new_run_dir(self):
        mod = load_script("earnings-qc-research")
        args = mod.build_parser().parse_args(["run", "--from-stage", "historical_option_pnl", "--years", "10"])
        with mock.patch.object(mod, "cmd_historical", return_value=7) as historical:
            rc = mod.cmd_run(args)
        self.assertEqual(rc, 7)
        historical.assert_called_once()

    def test_historical_uses_campaign_db_run_before_state_file_and_upserts_before_stage(self):
        mod = load_script("earnings-qc-research")
        run_dir = pathlib.Path(tempfile.mkdtemp())
        (run_dir / "full_summary.json").write_text(json.dumps({
            "ok": True,
            "status": "OK_FULL_QC_SCAN",
            "calendar_row_count": 1,
            "qc_symbols_scanned": 1,
            "forward_candidates": [{"symbol": "AAA"}],
            "final_candidates": [],
        }))
        args = mod.build_parser().parse_args(["historical", "--campaign", "camp-a", "--years", "10"])
        calls = []
        with mock.patch.object(mod, "require_research_db", return_value=True), \
             mock.patch.object(mod, "upsert_campaign", side_effect=lambda *a, **k: calls.append("campaign")), \
             mock.patch.object(mod, "upsert_run", side_effect=lambda *a, **k: calls.append("run")), \
             mock.patch.object(mod, "upsert_stage", side_effect=lambda *a, **k: calls.append("stage")), \
             mock.patch.object(mod, "run_multiyear_if_requested", return_value={"ok": True, "status": "OK_MULTIYEAR_OPTION_PNL_BACKTEST", "results": [{"symbol": "AAA", "status": "OK", "sample_size": 10, "win_rate": 0.6, "median_return_pct": 0.1, "mean_return_pct": 0.1, "max_drawdown_pct": 10, "max_loss_pct": -20}]}), \
             mock.patch.object(mod, "persist_summary_to_db", side_effect=lambda *a, **k: calls.append("persist")), \
             mock.patch.object(mod, "latest_db_run", return_value={"run_id": "db-run", "run_dir": str(run_dir)}), \
             mock.patch.object(mod, "latest_run_dir", side_effect=AssertionError("state file fallback should not be used when DB has a run")):
            rc = mod.cmd_historical(args)
        self.assertEqual(rc, 0)
        self.assertLess(calls.index("run"), calls.index("stage"))

    def test_historical_without_multiyear_artifact_does_not_succeed_from_stale_summary(self):
        mod = load_script("earnings-qc-research")
        run_dir = pathlib.Path(tempfile.mkdtemp())
        (run_dir / "full_summary.json").write_text(json.dumps({"ok": True, "status": "OK_FULL_QC_SCAN"}))
        args = mod.build_parser().parse_args(["historical", "--campaign", "camp-a", "--years", "10"])
        captured = {}
        with mock.patch.object(mod, "require_research_db", return_value=True), \
             mock.patch.object(mod, "upsert_campaign"), \
             mock.patch.object(mod, "upsert_run"), \
             mock.patch.object(mod, "upsert_stage"), \
             mock.patch.object(mod, "run_multiyear_if_requested", return_value=None), \
             mock.patch.object(mod, "persist_summary_to_db", side_effect=lambda *a, **k: captured.setdefault("summary", a[3])), \
             mock.patch.object(mod, "latest_db_run", return_value={"run_id": "db-run", "run_dir": str(run_dir)}):
            rc = mod.cmd_historical(args)
        self.assertEqual(rc, 2)
        self.assertFalse(captured["summary"]["ok"])
        self.assertEqual(captured["summary"]["status"], "BLOCKED_MULTIYEAR_OPTION_PNL_BACKTEST")
        self.assertTrue(captured["summary"]["multiyear_failed"])

    def test_multiyear_expansion_can_turn_historical_blocker_into_ok(self):
        multi = (SCRIPTS / "earnings-qc-multiyear-backtest").read_text()
        self.assertIn("scanner_failed", multi)
        self.assertIn("'MULTIYEAR' not in str(x.get('status'))", multi)
        self.assertIn("base_scan_ok", multi)
        self.assertIn("no_pass = bool(src) and bool(base_scan_ok)", multi)
        self.assertIn("full['ok']=bool(base_scan_ok) and bool(summary.get('ok'))", multi)
        self.assertNotIn("full['ok']=bool(full.get('ok')) and bool(summary.get('ok'))", multi)

    def test_stage_counts_are_integer_coerced_before_sql(self):
        mod = load_script("earnings-qc-research")
        self.assertEqual(mod.sql_int_or_null(3), "3")
        self.assertEqual(mod.sql_int_or_null("4"), "4")
        self.assertEqual(mod.sql_int_or_null("1; DROP TABLE x"), "NULL")
        cli = (SCRIPTS / "earnings-qc-research").read_text()
        self.assertIn("{sql_int_or_null(passed)}, {sql_int_or_null(failed)}", cli)

    def test_db_persistence_is_strict_for_mutating_runs(self):
        cli = (SCRIPTS / "earnings-qc-research").read_text()
        self.assertIn("DB_STRICT = False", cli)
        self.assertIn("raise RuntimeError('psql not found for required research DB persistence')", cli)
        self.assertIn("DB_STRICT = True", cli)
        self.assertIn("DB_RUN_PERSIST_FAILED", cli)
        self.assertIn("DB_SUMMARY_PERSIST_FAILED", cli)

    def test_db_latest_orders_by_updated_at_for_resumed_runs(self):
        cli = (SCRIPTS / "earnings-qc-research").read_text()
        self.assertIn("ORDER BY updated_at DESC, created_at DESC LIMIT 1", cli)
        self.assertIn("ORDER BY updated_at DESC, created_at DESC LIMIT {int(limit)}", cli)
        self.assertNotIn("ORDER BY created_at DESC LIMIT 1", cli)

    def test_status_run_dir_uses_run_dir_name_for_stage_lookup(self):
        mod = load_script("earnings-qc-research")
        run_dir = pathlib.Path(tempfile.mkdtemp()) / "older-run"
        run_dir.mkdir()
        seen = {}
        args = types.SimpleNamespace(campaign="camp", run_dir=str(run_dir), run_id=None, chunk_size=25, pretty=False)
        with mock.patch.object(mod, "latest_db_run", return_value={"run_id": "latest-run", "run_dir": "/tmp/latest"}), \
             mock.patch.object(mod, "load_chunks", return_value=[]), \
             mock.patch.object(mod, "aggregate", return_value={"ok": True}), \
             mock.patch.object(mod, "db_stages", side_effect=lambda run_id: seen.setdefault("run_id", run_id) or []), \
             contextlib.redirect_stdout(io.StringIO()):
            rc = mod.cmd_status(args)
        self.assertEqual(rc, 0)
        self.assertEqual(seen["run_id"], "older-run")

    def test_decision_add_reports_db_insert_failure(self):
        mod = load_script("earnings-qc-research")
        args = mod.build_parser().parse_args([
            "decision", "add",
            "--campaign", "new-campaign",
            "--type", "test_decision",
            "--rationale", "testing failure path",
        ])
        buf = io.StringIO()
        with mock.patch.object(mod, "ensure_research_db", return_value=True), \
             mock.patch.object(mod, "upsert_campaign", return_value=None), \
             mock.patch.object(mod, "db_exec", return_value=None), \
             contextlib.redirect_stdout(buf):
            rc = mod.cmd_decision_add(args)
        self.assertEqual(rc, 1)
        self.assertIn("DB_INSERT_FAILED", buf.getvalue())

    def test_decision_add_upserts_campaign_before_insert(self):
        mod = load_script("earnings-qc-research")
        args = mod.build_parser().parse_args([
            "decision", "add",
            "--campaign", "existing-campaign",
            "--type", "relax_min_bid",
            "--rationale", "document why",
            "--parameter-changes-json", '{"QC_MIN_BID":{"from":0.05,"to":0.02}}',
        ])
        buf = io.StringIO()
        with mock.patch.object(mod, "ensure_research_db", return_value=True), \
             mock.patch.object(mod, "upsert_campaign", return_value=None) as upsert, \
             mock.patch.object(mod, "db_exec", return_value=""), \
             contextlib.redirect_stdout(buf):
            rc = mod.cmd_decision_add(args)
        self.assertEqual(rc, 0)
        upsert.assert_called_once()
        self.assertIn('"ok": true', buf.getvalue())

    def test_deploy_verifies_research_runs_regclass_exactly(self):
        workflow = pathlib.Path('.github/workflows/vps-deploy.yml').read_text()
        self.assertIn("-qAt -c \"SELECT to_regclass('earnings_cache.research_runs') IS NOT NULL\" | grep -qx t", workflow)

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
        self.assertIn("def emit_and_quit", main)
        self.assertNotIn("def historical_runup_pass", main)
        self.assertNotIn("historical_contract_pass_debug_only", main)
        self.assertNotIn("historical_runup_pass", main)
        self.assertIn("FORWARD_LIQUIDITY_GREEKS_PASS_REQUIRES_MULTIYEAR_OPTION_PNL", main)

    def test_stage2_accepts_dynamic_liquidity_tuning_from_env_or_args(self):
        mod = load_script("earnings-qc-options-scan")
        import os
        old_env = {k: os.environ.get(k) for k in [spec[0] for spec in mod.TUNING_SPECS.values()]}
        try:
            for k in old_env:
                os.environ.pop(k, None)
            self.assertEqual(mod.scan_tuning_from_env()["max_premium"], 0.5)
        finally:
            for k, v in old_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_qc_stage2_project(
            project_dir,
            [{"symbol": "OPEN", "report_date": "2026-08-04"}],
            datetime.date(2026, 7, 14),
            {
                "max_premium": 0.75,
                "min_bid": 0.02,
                "max_spread_pct": 0.80,
                "min_relative_spread": 0.20,
                "vol_spread_factor": 0.70,
                "expected_move_spread_fraction": 0.25,
            },
        )
        main = (project_dir / "main.py").read_text()
        self.assertIn("self.max_premium = 0.750000", main)
        self.assertIn("self.min_bid = 0.020000", main)
        self.assertIn("self.max_spread_pct = 0.800000", main)
        self.assertIn("self.min_relative_spread = 0.200000", main)
        self.assertIn("self.vol_spread_factor = 0.700000", main)
        self.assertIn("self.expected_move_spread_fraction = 0.250000", main)

    def test_stage2_dynamic_premium_uses_threshold_neutral_metric_names(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        full = (SCRIPTS / "earnings-qc-research").read_text()
        self.assertIn("calls_under_max_premium", scan)
        self.assertIn("04_qc_calls_ask_under_max_premium", scan)
        self.assertIn("04_qc_calls_ask_under_max_premium", full)
        self.assertNotIn("calls_under_50c", scan)
        self.assertNotIn("04_qc_calls_ask_under_50c", scan)
        self.assertNotIn("04_qc_calls_ask_under_50c", full)


    def test_stage2_dynamic_tuning_is_guardrailed(self):
        mod = load_script("earnings-qc-options-scan")
        import os
        old = os.environ.get("QC_MAX_PREMIUM")
        try:
            os.environ["QC_MAX_PREMIUM"] = "10"
            with self.assertRaises(ValueError):
                mod.scan_tuning_from_env()
            os.environ["QC_MAX_PREMIUM"] = "nan"
            with self.assertRaises(ValueError):
                mod.scan_tuning_from_env()
            os.environ["QC_MAX_PREMIUM"] = "inf"
            with self.assertRaises(ValueError):
                mod.scan_tuning_from_env()
            with self.assertRaises(ValueError):
                mod.validate_scan_tuning({"max_premium": float("nan")})
            with self.assertRaises(ValueError):
                mod.validate_scan_tuning({"max_premium": 10})
            with self.assertRaises(ValueError):
                mod.validate_scan_tuning({"unknown": 1})
        finally:
            if old is None:
                os.environ.pop("QC_MAX_PREMIUM", None)
            else:
                os.environ["QC_MAX_PREMIUM"] = old

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

    def test_multiyear_generated_qc_algorithm_embeds_json_safely(self):
        mod = load_script("earnings-qc-multiyear-backtest")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_project(
            project_dir,
            [
                {
                    "symbol": "NULLT",
                    "earnings_date": "2026-08-04",
                    "spot": 10.0,
                    "contracts": [{"strike": 12, "ask": 0.25, "required_move_pct": None, "days_after_earnings": 3}],
                }
            ],
            8,
        )
        main = (project_dir / "main.py").read_text()
        self.assertIn("self.candidates = json.loads(", main)
        self.assertIn('required_move_pct": null', main)
        self.assertIn("self.candidates = json.loads('[{", main)
        compile(main, str(project_dir / "main.py"), "exec")

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
        mod = load_script("earnings-qc-research")
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
        self.assertFalse(summary["multiyear_failed"])
        self.assertTrue(summary["historical_gate_no_pass"])
        self.assertEqual(summary["status"], "NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL")
        self.assertEqual(summary["final_candidate_count"], 0)

    def test_full_scan_load_chunks_uses_latest_retry_for_same_offset(self):
        mod = load_script("earnings-qc-research")
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
        full = load_script("earnings-qc-research")
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
        self.assertIn("open_interest_volume_policy=\"diagnostic_warning_only_not_gate\"", main)
        self.assertIn("spread_policy=\"volatility_aware_relative_expected_move_no_absolute_spread_gate\"", main)
        self.assertIn("liquidity_fail_reasons=\"gate_only\"", main)
        self.assertIn("liquidity_warnings=\"zero_volume_zero_open_interest\"", main)
        self.assertIn("liquidity_fail_reason_counts", main)
        self.assertIn("liquidity_warning_counts", main)
        self.assertIn("cheap_contract_diagnostics_sample", main)
        self.assertIn("low_bid", main)
        self.assertIn("missing_greeks", main)
        self.assertIn("missing_iv", main)
        self.assertIn("spread_too_wide", main)
        self.assertIn("zero_volume", main)
        self.assertIn("zero_open_interest", main)
        self.assertNotIn("diagnostic_zero_volume", main)
        self.assertNotIn("diagnostic_zero_open_interest", main)
        self.assertIn('"liquidity_fail_reason_counts": {}, "liquidity_warning_counts": {"no_option_chain_slice_or_no_data": 1}', main)


    def test_full_scan_removed_last_year_debug_runup_metric(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        full = (SCRIPTS / "earnings-qc-research").read_text()
        self.assertNotIn("historical_required_move_runup_pass", scan)
        self.assertNotIn("historical_required_move_runup_pass", full)
        self.assertNotIn("historical_runup_source", scan)
        self.assertNotIn("runup_pct_debug_only", scan)
        self.assertNotIn("historical_contract_pass_debug_only", scan)
        self.assertNotIn("historical_threshold", scan)
        self.assertNotIn("debug_only_contract_required_move_pct", scan)

    def test_stage2_notify_only_candidates_or_blockers(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        self.assertIn("if notify and (payload.get('candidate_count') or not payload.get('ok'))", scan)

    def test_retry_failed_uses_end_to_end_runner(self):
        full = (SCRIPTS / "earnings-qc-research").read_text()
        self.assertIn("run_chunk_end_to_end(run_dir, off, args.chunk_size, args.years, args.end_to_end)", full)
        self.assertIn("rf.add_argument('--end-to-end'", full)

    def test_full_scan_throttles_discovery_and_sequential_chunks(self):
        full = (SCRIPTS / "earnings-qc-research").read_text()
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
        full = (SCRIPTS / "earnings-qc-research").read_text()
        self.assertIn("mb.get('ok') is False", full)
        self.assertIn("mandatory multiyear option-PnL backtest failed", full)
        self.assertIn("summary.get('historical_failed_chunks')", full)
        self.assertIn("deduped", full)

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
        full = (SCRIPTS / "earnings-qc-research").read_text()
        self.assertIn("--calendar-snapshot", scan)
        self.assertIn("calendar_rows.json", scan)
        self.assertIn("calendar_snapshot.json", full)
        self.assertIn("--calendar-snapshot", full)

    def test_symbol_filtered_runs_are_supported_by_public_cli_and_stage2(self):
        scan = load_script("earnings-qc-options-scan")
        full = load_script("earnings-qc-research")
        self.assertEqual(full.normalize_symbols_arg(" aapl, MSFT;AAPL "), ["AAPL", "MSFT"])
        self.assertEqual(scan.normalize_symbols_arg(" ttd,qbts "), ["TTD", "QBTS"])
        rows = [
            {"symbol": "TTD", "report_date": "2026-08-07"},
            {"symbol": "QBTS", "report_date": "2026-08-06"},
            {"symbol": "AAPL", "report_date": "2026-08-01"},
        ]
        self.assertEqual(scan.filter_calendar_rows_by_symbols(rows, ["QBTS", "TTD"]), rows[:2])
        src_full = (SCRIPTS / "earnings-qc-research").read_text()
        src_scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        self.assertIn("r.add_argument('--symbols'", src_full)
        self.assertIn("cmd += ['--symbols', ','.join(symbols)]", src_full)
        self.assertIn("[--calendar-snapshot PATH] [--symbols AAPL,MSFT]", src_scan)
        self.assertIn("'requested_symbols': requested_symbols", src_scan)

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
        full = load_script("earnings-qc-research")
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



    def test_scanner_cli_accepts_max_premium_below_half_dollar(self):
        mod = load_script("earnings-qc-options-scan")
        captured = {}
        mod.run_now = lambda **kwargs: captured.update(kwargs) or 0
        old_argv = sys.argv
        try:
            sys.argv = ["earnings-qc-options-scan", "run-now", "--no-outbox", "--max-premium", "0.25", "--min-bid", "0.01"]
            rc = mod.main()
        finally:
            sys.argv = old_argv
        self.assertEqual(rc, 0)
        self.assertEqual(captured["tuning"]["max_premium"], 0.25)
        self.assertEqual(captured["tuning"]["min_bid"], 0.01)

    def test_parse_stage2_params_is_idempotent_after_normalization(self):
        mod = load_script("earnings-qc-options-scan")
        raw = mod.parse_stage2_params(strike_range="-20:100", delta_range="0.05:0.35", iv_range="0.1:2.5", min_open_interest=10, min_volume=5)
        again = mod.parse_stage2_params(**raw)
        self.assertEqual(again["strike_min"], -20)
        self.assertEqual(again["strike_max"], 100)
        self.assertEqual(again["delta_min"], 0.05)
        self.assertEqual(again["iv_max"], 2.5)
        self.assertEqual(again["min_open_interest_gate"], 10)
        self.assertEqual(again["min_volume_gate"], 5)




    def test_cmd_run_candidate_scan_only_does_not_fail_historical_gate(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        mod.STATE_DIR = tmp / "state"
        mod.require_research_db = lambda: True
        mod.upsert_campaign = lambda *a, **k: None
        mod.upsert_run = lambda *a, **k: None
        mod.latest_db_run = lambda campaign: {"run_id": "rid", "run_dir": str(tmp)}
        mod.discover_calendar_total = lambda *a, **k: 1
        mod.run_chunks_parallel = lambda *a, **k: None
        mod.write_summary = lambda run_dir, batch_size, notify=False: {"ok": False, "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE", "forward_candidate_count": 1, "candidate_count": 0}
        persisted = []
        mod.persist_summary_to_db = lambda campaign_id, run_id, run_dir, summary, params: persisted.append(summary.copy())
        mod.run_multiyear_if_requested = lambda *a, **k: None
        args = mod.build_parser().parse_args(["run", "--run-dir", str(tmp), "--run-id", "rid", "--to-stage", "candidate-scan", "--no-end-to-end", "--no-outbox"])
        rc = mod.cmd_run(args)
        self.assertEqual(rc, 0)
        self.assertEqual(persisted[-1]["status"], "OK_CANDIDATE_SCAN_REQUIRES_HISTORICAL_OPTION_PNL")
        self.assertTrue(persisted[-1]["ok"])

    def test_cmd_run_from_qc_chain_scan_runs_start_offset_from_snapshot(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "calendar_snapshot.json").write_text(json.dumps([{"symbol": "OPEN", "report_date": "2026-08-04"}]))
        calls = []
        mod.STATE_DIR = tmp / "state"
        mod.require_research_db = lambda: True
        mod.upsert_campaign = lambda *a, **k: None
        mod.upsert_run = lambda *a, **k: None
        mod.latest_db_run = lambda campaign: {"run_id": "rid", "run_dir": str(tmp)}
        mod.run_chunks_parallel = lambda run_dir, offsets, batch_size, parallel, years, end_to_end, symbols, args=None: calls.append(list(offsets))
        mod.write_summary = lambda run_dir, batch_size, notify=False: {"ok": True, "status": "OK_FULL_QC_SCAN"}
        mod.persist_summary_to_db = lambda *a, **k: None
        mod.run_multiyear_if_requested = lambda *a, **k: None
        args = mod.build_parser().parse_args(["run", "--run-dir", str(tmp), "--run-id", "rid", "--from-stage", "qc-chain", "--to-stage", "candidate-scan", "--chunk-size", "25", "--max-chunks", "1", "--no-end-to-end"])
        rc = mod.cmd_run(args)
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [[0]])


    def test_cmd_run_rejects_put_or_both_for_historical_until_supported(self):
        mod = load_script("earnings-qc-research")
        mod.require_research_db = lambda: (_ for _ in ()).throw(AssertionError("db should not be touched"))
        for right in ["put", "both"]:
            args = mod.build_parser().parse_args(["run", "--option-right", right, "--end-to-end"])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = mod.cmd_run(args)
            self.assertEqual(rc, 2)
            self.assertIn("STAGE_NOT_IMPLEMENTED_FOR_HISTORICAL_OPTION_RIGHT", buf.getvalue())

    def test_cmd_run_rejects_unimplemented_stage_ranges_before_db(self):
        mod = load_script("earnings-qc-research")
        mod.require_research_db = lambda: (_ for _ in ()).throw(AssertionError("db should not be touched"))
        args = mod.build_parser().parse_args(["run", "--from-stage", "candidate-scan", "--to-stage", "candidate-scan"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = mod.cmd_run(args)
        self.assertEqual(rc, 2)
        self.assertIn("STAGE_NOT_IMPLEMENTED_FOR_RUN_START", buf.getvalue())
        args = mod.build_parser().parse_args(["run", "--to-stage", "intraday"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = mod.cmd_run(args)
        self.assertEqual(rc, 2)
        self.assertIn("STAGE_NOT_IMPLEMENTED_FOR_RUN_TARGET", buf.getvalue())

    def test_chunk_multiyear_forwards_historical_params(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        fake = tmp / "multi.py"
        fake.write_text("#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps({'ok': True, 'argv': sys.argv[1:]}))\n")
        fake.chmod(0o755)
        mod.MULTIYEAR = fake
        chunk = {"_chunk_offset": 0, "candidate_details": [{"symbol": "OPEN", "earnings_date": "2026-08-04", "contracts": []}], "funnel": {}}
        args = argparse.Namespace(entry_window="14:28", exit_days_before="2", exit_policy="before-earnings", historical_resolution="minute", max_contracts=3, path_metrics="intraday")
        out = mod.run_chunk_multiyear(tmp, chunk, years=9, args=args)
        argv = out["argv"]
        self.assertIn("--entry-window", argv)
        self.assertIn("14:28", argv)
        self.assertIn("--historical-resolution", argv)
        self.assertIn("minute", argv)
        self.assertIn("--max-contracts", argv)
        self.assertIn("3", argv)

    def test_run_now_passes_calendar_window_and_stage2_params_to_probe(self):
        mod = load_script("earnings-qc-options-scan")
        calls = []
        old_root = mod.REPORT_ROOT
        mod.REPORT_ROOT = pathlib.Path(tempfile.mkdtemp())
        mod.nasdaq_calendar_window = lambda start, end: ([{"symbol": "OPEN", "report_date": end.isoformat()}], [{"start": start.isoformat(), "end": end.isoformat()}])
        mod.qc_capability_probe = lambda rows, run_dir, batch_limit, today, batch_offset=0, stage2_params=None, tuning=None: calls.append((rows, batch_limit, today, batch_offset, stage2_params, tuning)) or {"qc_option_chain_batch_diagnostic": {"ok": True, "runtime_statistics": {"trader.candidates": "0", "trader.symbols_input": "1"}, "symbols_requested": 1, "parsed_result": {"rows": [{"symbol": "OPEN"}]}}}
        try:
            rc = mod.run_now(notify=False, qc_batch_limit=1, as_of_date="2026-07-01", calendar_from_days=10, calendar_to_days=12, stage2_params={"option_resolution": "minute", "option_right": "both", "strike_range": "-20:100"}, tuning={"max_premium": 0.25, "min_bid": 0.01})
        finally:
            mod.REPORT_ROOT = old_root
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2], datetime.date(2026, 7, 1))
        self.assertEqual(calls[0][4]["option_resolution"], "minute")
        self.assertEqual(calls[0][5]["max_premium"], 0.25)
        result_files = list(mod.REPORT_ROOT.glob("*/result.json"))
        self.assertEqual(result_files, [])

    def test_research_cli_stage_addressable_rich_qc_params(self):
        mod = load_script("earnings-qc-research")
        args = mod.build_parser().parse_args([
            "run", "--from-stage", "chain", "--to-stage", "candidate-scan",
            "--symbols", "TTD,QBTS", "--qc-resolution", "daily", "--option-resolution", "hour",
            "--strike-range", "-20:100", "--option-right", "both", "--delta-range", "0.05:0.35",
            "--iv-range", "0.10:2.50", "--min-open-interest", "10", "--min-volume", "5", "--max-premium", "0.25", "--min-bid", "0.01",
            "--no-end-to-end",
        ])
        params = mod.current_parameters(args)
        self.assertEqual(args.from_stage, "chain")
        self.assertEqual(args.to_stage, "candidate-scan")
        self.assertEqual(params["qc_resolution"], "daily")
        self.assertEqual(params["option_right"], "both")
        self.assertEqual(params["delta_range"], "0.05:0.35")
        self.assertEqual(params["max_premium"], 0.25)
        self.assertEqual(params["min_bid"], 0.01)

    def test_stage2_generated_qc_algorithm_uses_rich_parameters(self):
        mod = load_script("earnings-qc-options-scan")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_qc_stage2_project(
            project_dir,
            [{"symbol": "OPEN", "report_date": "2026-08-04"}],
            datetime.date(2026, 7, 14),
            stage2_params={
                "qc_resolution": "daily",
                "option_resolution": "hour",
                "strike_range": "-20:100",
                "option_right": "both",
                "delta_range": "0.05:0.35",
                "iv_range": "0.10:2.50",
                "min_open_interest": 10,
                "min_volume": 5,
            },
        )
        main = (project_dir / "main.py").read_text()
        self.assertIn("self.add_equity(ticker, Resolution.DAILY)", main)
        self.assertIn("self.add_option(ticker, Resolution.HOUR)", main)
        self.assertIn("strikes(-20, 100).expiration(0, 120)", main)
        self.assertIn("self.option_right = 'both'", main)
        self.assertIn("self.delta_min = 0.05", main)
        self.assertIn("failure_reasons.append(\"delta_out_of_range\")", main)
        self.assertIn("failure_reasons.append(\"low_open_interest\")", main)


class EarningsQcHistoricalObservabilityTests(unittest.TestCase):

    def test_refresh_summary_after_historical_marks_terminal_no_pass_not_blocked(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "full_summary.json").write_text(json.dumps({
            "ok": False,
            "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE",
            "calendar_row_count": 2,
            "calendar_universe_count": 2,
            "qc_symbols_scanned": 2,
            "failed_chunks": [{"status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE"}],
            "failed_chunk_count": 1,
            "aggregate_funnel": {},
            "forward_candidates": [{"symbol": "TE"}],
            "final_candidates": [],
        }))
        mb = {"ok": False, "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE_NO_PASSING_SYMBOLS", "results": [{"symbol": "TE", "sample_size": 4}]}
        out = mod.refresh_summary_after_historical(tmp, mb)
        self.assertEqual(out["status"], "NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL")
        self.assertTrue(out["historical_gate_ran"])
        self.assertTrue(out["historical_gate_no_pass"])
        self.assertFalse(out["historical_gate_blocked"])
        self.assertFalse(out["multiyear_failed"])
        self.assertEqual(out["failed_chunk_count"], 0)

    def test_chunked_aggregate_marks_terminal_no_pass_not_infra_failure(self):
        mod = load_script("earnings-qc-research")
        chunk = {
            "ok": True,
            "calendar_row_count": 1,
            "calendar_universe_count": 1,
            "qc_processed_row_count": 1,
            "candidate_details": [{"symbol": "TE", "earnings_date": "2026-08-01"}],
            "funnel": {},
            "chunk_multiyear_backtest": {"ok": False, "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE_NO_PASSING_SYMBOLS", "results": [{"symbol": "TE"}]},
        }
        out = mod.aggregate([chunk])
        self.assertEqual(out["status"], "NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL")
        self.assertEqual(out["failed_chunk_count"], 0)
        self.assertTrue(out["historical_gate_ran"])
        self.assertTrue(out["historical_gate_no_pass"])
        self.assertFalse(out["historical_gate_blocked"])
        self.assertFalse(out["multiyear_failed"])

    def test_refresh_summary_no_forward_candidates_is_not_multiyear_infra_failure(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "full_summary.json").write_text(json.dumps({
            "ok": False,
            "status": "NO_FORWARD_CANDIDATES",
            "calendar_row_count": 2,
            "calendar_universe_count": 2,
            "qc_symbols_scanned": 2,
            "failed_chunks": [],
            "failed_chunk_count": 0,
            "aggregate_funnel": {},
            "forward_candidates": [],
            "final_candidates": [],
        }))
        mb = {"ok": False, "status": "NO_FORWARD_CANDIDATES", "results": []}
        out = mod.refresh_summary_after_historical(tmp, mb)
        self.assertEqual(out["status"], "NO_FORWARD_CANDIDATES")
        self.assertFalse(out["historical_gate_blocked"])
        self.assertFalse(out["multiyear_failed"])
        self.assertEqual(out["failed_chunk_count"], 0)

    def test_chunked_no_pass_does_not_mask_scanner_failures(self):
        mod = load_script("earnings-qc-research")
        out = mod.aggregate([
            {
                "ok": False,
                "status": "BLOCKED_QC_BATCH_FAILED",
                "blocked_reason": "QC batch failed",
                "calendar_row_count": 2,
                "calendar_universe_count": 2,
                "qc_processed_row_count": 1,
                "candidate_details": [],
                "funnel": {},
            },
            {
                "ok": True,
                "calendar_row_count": 2,
                "calendar_universe_count": 2,
                "qc_processed_row_count": 1,
                "candidate_details": [{"symbol": "TE", "earnings_date": "2026-08-01"}],
                "funnel": {},
                "chunk_multiyear_backtest": {"ok": False, "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE_NO_PASSING_SYMBOLS", "results": [{"symbol": "TE"}]},
            },
        ])
        self.assertNotEqual(out["status"], "NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL")
        self.assertEqual(out["status"], "PARTIAL_FULL_QC_SCAN")
        self.assertEqual(out["failed_chunk_count"], 1)
        self.assertFalse(out["historical_gate_no_pass"])

    def test_chunked_ok_multiyear_without_matching_final_candidates_is_not_ok(self):
        mod = load_script("earnings-qc-research")
        out = mod.aggregate([{
            "ok": True,
            "calendar_row_count": 1,
            "calendar_universe_count": 1,
            "qc_processed_row_count": 1,
            "candidate_details": [{"symbol": "TE", "earnings_date": "2026-08-01"}],
            "funnel": {},
            "chunk_multiyear_backtest": {"ok": True, "status": "OK_MULTIYEAR_OPTION_PNL_BACKTEST", "results": [{"symbol": "OTHER", "sample_size": 12, "win_rate": 0.8, "median_return_pct": 0.1}]},
        }])
        self.assertFalse(out["ok"])
        self.assertEqual(out["final_candidate_count"], 0)
        self.assertEqual(out["status"], "BLOCKED_HISTORICAL_OPTION_PNL_GATE")

    def test_chunked_no_pass_requires_all_candidate_chunks_validated(self):
        mod = load_script("earnings-qc-research")
        out = mod.aggregate([
            {
                "ok": True,
                "calendar_row_count": 2,
                "calendar_universe_count": 2,
                "qc_processed_row_count": 1,
                "candidate_details": [{"symbol": "TE", "earnings_date": "2026-08-01"}],
                "funnel": {},
            },
            {
                "ok": True,
                "calendar_row_count": 2,
                "calendar_universe_count": 2,
                "qc_processed_row_count": 1,
                "candidate_details": [{"symbol": "WMT", "earnings_date": "2026-08-01"}],
                "funnel": {},
                "chunk_multiyear_backtest": {"ok": False, "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE_NO_PASSING_SYMBOLS", "results": [{"symbol": "WMT"}]},
            },
        ])
        self.assertFalse(out["historical_gate_no_pass"])
        self.assertEqual(out["candidate_chunk_count"], 2)
        self.assertEqual(out["validated_candidate_chunk_count"], 1)
        self.assertEqual(out["status"], "BLOCKED_HISTORICAL_OPTION_PNL_GATE")

    def test_refresh_summary_no_pass_does_not_mask_scanner_failures(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "full_summary.json").write_text(json.dumps({
            "ok": False,
            "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE",
            "calendar_row_count": 2,
            "calendar_universe_count": 2,
            "qc_symbols_scanned": 1,
            "failed_chunks": [{"status": "BLOCKED_QC_BATCH_FAILED", "blocked_reason": "QC batch failed"}],
            "failed_chunk_count": 1,
            "aggregate_funnel": {},
            "forward_candidates": [{"symbol": "TE"}],
            "final_candidates": [],
        }))
        mb = {"ok": False, "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE_NO_PASSING_SYMBOLS", "results": [{"symbol": "TE"}]}
        out = mod.refresh_summary_after_historical(tmp, mb)
        self.assertNotEqual(out["status"], "NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL")
        self.assertEqual(out["status"], "BLOCKED_HISTORICAL_OPTION_PNL_GATE")
        self.assertEqual(out["failed_chunk_count"], 1)
        self.assertFalse(out["historical_gate_no_pass"])

    def test_refresh_summary_ok_multiyear_without_matching_final_candidates_is_blocked(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "full_summary.json").write_text(json.dumps({
            "ok": False,
            "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE",
            "calendar_row_count": 1,
            "calendar_universe_count": 1,
            "qc_symbols_scanned": 1,
            "failed_chunks": [],
            "failed_chunk_count": 0,
            "aggregate_funnel": {},
            "forward_candidates": [{"symbol": "TE"}],
            "final_candidates": [],
        }))
        mb = {"ok": True, "status": "OK_MULTIYEAR_OPTION_PNL_BACKTEST", "results": [{"symbol": "OTHER", "sample_size": 12, "win_rate": 0.8, "median_return_pct": 0.1}]}
        out = mod.refresh_summary_after_historical(tmp, mb)
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "BLOCKED_HISTORICAL_OPTION_PNL_GATE")
        self.assertTrue(out["historical_gate_blocked"])
        self.assertEqual(out["final_candidate_count"], 0)

    def test_qc_cloud_extract_generates_underlying_ohlcv_and_realized_vol_fields(self):
        script = (ROOT / "agent-platform" / "scripts" / "trading-research-qc-cloud-extract").read_text()
        self.assertIn("underlying_history_rows", script)
        self.assertIn("realized_volatility", script)
        self.assertIn("sample_time", script)
        self.assertIn("underlying_price", script)
        self.assertIn("candidate_event_context", script)
        self.assertIn("target_event_windows", script)
        self.assertIn("event_underlying_windows", script)
        self.assertIn("event_aligned_backtest_request", script)
        self.assertIn("event_plan_produced_quote_slices_bounded", script)
        self.assertIn("historical_option_chain_event_slices_only_if_event_is_inside_bounded_backtest_window", script)

    def test_skill_prioritizes_daily_historical_before_side_ideas(self):
        skill = (ROOT / "agent-platform" / "skills" / "trader-research-system" / "SKILL.md").read_text()
        self.assertIn("absolute priority over side ideas", skill)
        self.assertIn("NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL", skill)

    def test_vps_deploy_grants_ubuntu_read_acl_for_research_observability(self):
        workflow = (ROOT / ".github" / "workflows" / "vps-deploy.yml").read_text()
        self.assertIn("DEPLOY_USER='$VPS_USER' bash -s", workflow)
        self.assertIn("setfacl -m \"u:${DEPLOY_USER}:x\" /agents/research", workflow)
        self.assertIn("setfacl -Rm \"u:${DEPLOY_USER}:rx,d:u:${DEPLOY_USER}:rx\" /agents/research/state /agents/research/logs /agents/research/reports", workflow)
        self.assertIn("sudo -n -u \"$DEPLOY_USER\"", workflow)
        self.assertIn("test -x /agents/research", workflow)
        self.assertIn("test -r /agents/research/state", workflow)


class EarningsQcFailedChunkClassificationTests(unittest.TestCase):
    def test_refresh_moves_historical_failures_out_of_scanner_failed_chunks(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "full_summary.json").write_text(json.dumps({
            "calendar_row_count": 10,
            "calendar_universe_count": 10,
            "qc_symbols_scanned": 9,
            "aggregate_funnel": {},
            "forward_candidates": [{"symbol": "A"}],
            "failed_chunks": [
                {"offset": 1, "status": "QC_BACKTEST_FAILED", "blocked_reason": "mandatory multiyear option-PnL backtest failed"},
                {"offset": 2, "status": "BLOCKED_QC_BATCH_FAILED", "blocked_reason": "QC batch failed"},
            ],
        }))
        out = mod.refresh_summary_after_historical(tmp, {"ok": False, "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE_NO_PASSING_SYMBOLS", "results": []})
        self.assertEqual(out["failed_chunk_count"], 1)
        self.assertEqual(out["historical_failed_chunk_count"], 1)
        self.assertEqual(out["failed_chunks"][0]["status"], "BLOCKED_QC_BATCH_FAILED")

    def test_aggregate_ignores_stale_empty_batch_chunks_beyond_calendar_rows(self):
        mod = load_script("earnings-qc-research")
        out = mod.aggregate([
            {"_chunk_offset": 0, "ok": True, "calendar_row_count": 185, "calendar_universe_count": 185, "qc_processed_row_count": 185, "candidate_details": [], "funnel": {}},
            {"_chunk_offset": 650, "ok": False, "status": "BLOCKED_QC_BATCH_FAILED", "calendar_row_count": 185, "calendar_universe_count": 185, "qc_processed_row_count": 0, "qc_checks": {"qc_option_chain_batch_diagnostic": {"ok": False, "reason": "empty_batch"}}, "funnel": {}},
        ])
        self.assertEqual(out["failed_chunk_count"], 0)
        self.assertTrue(out["ok"])

    def test_aggregate_complete_scan_with_no_forward_candidates_is_terminal_ok(self):
        mod = load_script("earnings-qc-research")
        out = mod.aggregate([{
            "ok": True,
            "calendar_row_count": 1,
            "calendar_universe_count": 1,
            "qc_processed_row_count": 1,
            "candidate_details": [],
            "funnel": {},
        }])
        self.assertTrue(out["ok"])
        self.assertEqual(out["status"], "OK_FULL_QC_SCAN")
        self.assertEqual(out["forward_candidate_count"], 0)
        self.assertFalse(out["historical_gate_blocked"])
        self.assertFalse(out["historical_gate_no_pass"])

    def test_aggregate_separates_multiyear_infra_failures_from_scanner_chunks(self):
        mod = load_script("earnings-qc-research")
        out = mod.aggregate([{
            "ok": True,
            "calendar_row_count": 1,
            "qc_processed_row_count": 1,
            "candidate_details": [{"symbol": "A", "earnings_date": "2026-08-01"}],
            "funnel": {},
            "chunk_multiyear_backtest": {"ok": False, "status": "QC_BACKTEST_FAILED", "results": []},
        }])
        self.assertEqual(out["failed_chunk_count"], 0)
        self.assertEqual(out["historical_failed_chunk_count"], 1)
        self.assertTrue(out["multiyear_failed"])

if __name__ == "__main__":
    unittest.main()
