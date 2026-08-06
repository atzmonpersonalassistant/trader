import contextlib
import argparse
import datetime
import io
import json
import math
import os
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "agent-platform" / "scripts" / "earnings-qc-options"
PASSING_WINDOWS = [{"window": "1y", "status": "OK", "sample_size": 1}]


def load_script(name: str):
    path = SCRIPTS / name
    module_name = name.replace("-", "_")
    mod = types.ModuleType(module_name)
    mod.__file__ = str(path)
    mod.__loader__ = None
    mod.__package__ = ""
    exec(compile(path.read_bytes(), str(path), "exec"), mod.__dict__)
    return mod


class EarningsQcOptionsGeneratedCodeTests(unittest.TestCase):

    def build_multiyear_algorithm(self, params=None):
        mod = load_script("earnings-qc-multiyear-backtest")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        params = {
            "final_min_sample_size": 1,
            "min_open_interest": 0,
            "min_volume": 0,
            **(params or {}),
        }
        mod.write_project(project_dir, [{"symbol": "XYZ", "earnings_date": "2026-02-01"}], 1, params=params)
        main = (project_dir / "main.py").read_text()

        fake_imports = types.ModuleType("AlgorithmImports")

        class QCAlgorithm:
            def set_runtime_statistic(self, key, value):
                self.runtime_statistics[key] = value

            def debug(self, message):
                self.debug_messages.append(message)

        fake_imports.QCAlgorithm = QCAlgorithm
        fake_imports.Resolution = types.SimpleNamespace(DAILY="Daily")
        fake_imports.OptionRight = types.SimpleNamespace(CALL="call", PUT="put")
        data_source = types.ModuleType("QuantConnect.DataSource")
        data_source.EODHDUpcomingEarnings = object
        quantconnect = types.ModuleType("QuantConnect")
        old_imports = sys.modules.get("AlgorithmImports")
        old_qc = sys.modules.get("QuantConnect")
        old_data_source = sys.modules.get("QuantConnect.DataSource")
        sys.modules["AlgorithmImports"] = fake_imports
        sys.modules["QuantConnect"] = quantconnect
        sys.modules["QuantConnect.DataSource"] = data_source
        namespace = {}
        try:
            exec(compile(main, str(project_dir / "main.py"), "exec"), namespace)
        finally:
            if old_imports is None:
                sys.modules.pop("AlgorithmImports", None)
            else:
                sys.modules["AlgorithmImports"] = old_imports
            if old_qc is None:
                sys.modules.pop("QuantConnect", None)
            else:
                sys.modules["QuantConnect"] = old_qc
            if old_data_source is None:
                sys.modules.pop("QuantConnect.DataSource", None)
            else:
                sys.modules["QuantConnect.DataSource"] = old_data_source

        alg = namespace["EarningsQcHistoricalOptionPnl"]()
        alg.runtime_statistics = {}
        alg.debug_messages = []
        alg.errors = []
        alg.snapshots = {}
        alg.candidates = [{"symbol": "XYZ"}]
        alg.events = {
            "XYZ": {
                "2026-02-01": {
                    "symbol": "XYZ",
                    "report_date": "2026-02-01",
                    "report_time": "Before Market",
                }
            }
        }
        alg.exit_policy = "sell_before_earnings_no_hold_through"
        alg.contract_fields = ("symbol","strike","expiry","bid","ask","mid","last","volume","open_interest","iv","delta","right")
        alg.contract_field_index = {name: i for i, name in enumerate(alg.contract_fields)}
        alg.snapshot_contract_count = 0
        alg.snapshot_day_count = 0
        alg.snapshot_peak_day_count = 0
        alg.entry_min_days = 21
        alg.entry_max_days = 28
        alg.exit_days_before = mod.hist_params(params)["exit_days_before"]
        alg.max_days_after_earnings = 7
        alg.max_premium = 0.50
        alg.max_spread = 0.25
        alg.max_spread_pct = 0.60
        alg.min_relative_spread = 0.25
        alg.vol_spread_factor = 0.50
        alg.expected_move_spread_fraction = 0.15
        alg.min_bid = 0.05
        alg.min_open_interest = 0
        alg.min_volume = 0
        alg.option_right = mod.hist_params(params)["option_right"]
        alg.delta_target = mod.hist_params(params)["delta_target"]
        alg.stop_loss_max_loss_pct = mod.hist_params(params)["stop_loss_max_loss_pct"]
        return alg

    def quote(self, bid, ask=None, iv=0.40, symbol="XYZ_CALL_110", strike=110.0, right="call", delta=0.30, expiry="2026-02-05"):
        ask = bid if ask is None else ask
        return {
            "symbol": symbol,
            "strike": strike,
            "expiry": expiry,
            "bid": bid,
            "ask": ask,
            "mid": round((bid + ask) / 2.0, 4),
            "volume": 100,
            "open_interest": 100,
            "iv": iv,
            "delta": delta,
            "right": right,
        }

    def option_contract(self, symbol, right):
        return types.SimpleNamespace(
            symbol=symbol,
            right=right,
            strike=110.0,
            expiry=datetime.datetime(2026, 1, 20),
            bid_price=0.10,
            ask_price=0.20,
            last_price=0.15,
            volume=100,
            open_interest=100,
            implied_volatility=0.40,
            greeks=types.SimpleNamespace(delta=0.30),
        )

    def set_multiyear_snapshots(self, alg, quotes_by_day):
        rows = {}
        for day, quote in quotes_by_day.items():
            underlying = 100.0
            if isinstance(quote, tuple):
                underlying, quote = quote
            rows[day] = {"underlying": underlying, "contracts": [quote]}
        alg.snapshots = {"XYZ": rows}


    def test_single_public_research_cli_uses_internal_libexec_stages(self):
        cli = (SCRIPTS / "earnings-qc-research").read_text()
        self.assertIn("/agents/research/libexec/earnings-qc-options/earnings-qc-options-scan", cli)
        self.assertIn("/agents/research/libexec/earnings-qc-options/earnings-qc-multiyear-backtest", cli)
        self.assertNotIn("SCANNER = pathlib.Path('/agents/research/bin/earnings-qc-options-scan')", cli)
        self.assertNotIn("MULTIYEAR = pathlib.Path('/agents/research/bin/earnings-qc-multiyear-backtest')", cli)

    def test_research_db_exec_sends_large_sql_on_stdin(self):
        mod = load_script("earnings-qc-research")
        large_sql = "SELECT '" + ("x" * 200000) + "';"
        completed = types.SimpleNamespace(returncode=0, stdout="ok\n", stderr="")
        with mock.patch.object(mod.shutil, "which", return_value="/usr/bin/psql"), \
             mock.patch.object(mod.subprocess, "run", return_value=completed) as run:
            out = mod.db_exec(large_sql, fetch=True)

        self.assertEqual(out, "ok\n")
        args, kwargs = run.call_args
        self.assertNotIn("-c", args[0])
        self.assertEqual(kwargs["input"], large_sql)

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

    def test_current_parameters_records_bounded_no_outbox_provenance(self):
        mod = load_script("earnings-qc-research")
        args = mod.build_parser().parse_args(["run", "--max-chunks", "1", "--no-outbox"])
        args.from_stage = "calendar"
        args.to_stage = "historical_option_pnl"
        params = mod.current_parameters(args)
        self.assertEqual(params["max_chunks"], 1)
        self.assertIs(params["no_outbox"], True)

    def test_research_cli_has_postgres_persistence_schema(self):
        cli = (SCRIPTS / "earnings-qc-research").read_text()
        for table in ["research_campaigns", "research_runs", "research_stages", "stage_artifacts", "candidate_dossiers", "research_decisions", "cleanup_runs"]:
            self.assertIn(table, cli)
        self.assertIn("historical_option_pnl_years_", cli)
        self.assertIn("derive_insights", cli)
        self.assertIn("research_verdict TEXT", cli)
        self.assertIn("ADD COLUMN IF NOT EXISTS research_verdict TEXT", cli)
        self.assertIn("forward_candidate_count INTEGER NOT NULL DEFAULT 0", cli)
        self.assertIn("ADD COLUMN IF NOT EXISTS forward_candidate_count INTEGER NOT NULL DEFAULT 0", cli)
        self.assertIn("summary_json->>'forward_candidate_count'", cli)
        self.assertIn("forward_candidate_count IS DISTINCT FROM (summary_json->>'forward_candidate_count')::integer", cli)
        self.assertIn("ALTER COLUMN summary_json DROP NOT NULL", cli)
        self.assertIn("ALTER COLUMN contract_json DROP NOT NULL", cli)

    def test_research_schema_identifier_is_sanitized(self):
        mod = load_script("earnings-qc-research")
        self.assertEqual(mod.safe_identifier("earnings_cache", "fallback"), "earnings_cache")
        self.assertEqual(mod.safe_identifier("bad;drop schema public", "fallback"), "fallback")
        self.assertEqual(mod.safe_identifier("1bad", "fallback"), "fallback")

    def test_candidate_persistence_keeps_forward_leads_when_final_exists(self):
        mod = load_script("earnings-qc-research")
        calls = []
        summary = {
            "final_candidates": [{
                "symbol": "AAA",
                "earnings_date": "2026-08-01",
                "spot": 10.0,
                "contract_count": 1,
                "debug_full_candidate_only": "should_not_be_persisted",
                "contracts": [{
                    "contract": "AAA_CALL_11",
                    "bid": 0.10,
                    "ask": 0.20,
                    "required_move_pct": 10.0,
                    "iv": 0.55,
                    "debug_contract_only": "stays_in_contract_json_only",
                }],
            }],
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
        self.assertIn("ON CONFLICT (candidate_id)", joined)
        self.assertIn("contract_count", joined)
        self.assertIn("required_move_pct", joined)
        self.assertNotIn("debug_full_candidate_only", joined)
        self.assertEqual(len(calls), 2)

    def test_upsert_run_splits_lifecycle_verdict_and_bottleneck(self):
        mod = load_script("earnings-qc-research")
        calls = []
        ok_summary = {"ok": True, "status": "OK_FULL_QC_SCAN", "final_candidate_count": 1, "forward_candidate_count": 5}
        no_pass_summary = {"ok": False, "status": "NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL", "historical_gate_no_pass": True}
        blocked_summary = {"ok": False, "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE", "historical_gate_blocked": True}
        with mock.patch.object(mod, "ensure_research_db", return_value=True), \
             mock.patch.object(mod, "db_exec", side_effect=lambda sql: calls.append(sql) or ""):
            mod.upsert_run("ok-run", "camp", "completed", pathlib.Path("/tmp/ok"), {}, ok_summary, finished=True)
            mod.persist_summary_to_db("camp", "no-pass-run", pathlib.Path("/tmp/no-pass"), no_pass_summary, {})
            mod.upsert_run("blocked-run", "camp", "blocked", pathlib.Path("/tmp/blocked"), {}, blocked_summary, finished=True)
        joined = "\n".join(calls)
        self.assertIn("final_candidate_count,forward_candidate_count,research_verdict,bottleneck,error", joined)
        self.assertIn("1, 5, 'OK_FULL_QC_SCAN', NULL, NULL", joined)
        self.assertIn("'no-pass-run', 'camp', 'completed'", joined)
        self.assertIn("'NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL', NULL, NULL", joined)
        self.assertIn("'BLOCKED_HISTORICAL_OPTION_PNL_GATE', 'BLOCKED_HISTORICAL_OPTION_PNL_GATE', NULL", joined)

    def test_cleanup_prunes_old_db_blobs_without_deleting_rows(self):
        mod = load_script("earnings-qc-research")
        reports = pathlib.Path(tempfile.mkdtemp())
        old_scan = reports / "earnings-qc-options-scan-full-old"
        old_pass = reports / "research-pass-old"
        old_experiment = reports / "qc-run-old"
        for path in [old_scan, old_pass, old_experiment]:
            path.mkdir()
            (path / "payload.txt").write_text("old")
            if path.name.startswith("research-pass-"):
                (path / "final_report.md").write_text("discard\n")
                (path / "exit_code").write_text("0\n")
            if path.name.startswith("qc-run-"):
                (path / "qc_run_result.json").write_text(json.dumps({"ok": True}))
            os.utime(path, (1, 1))
            os.utime(path / "payload.txt", (1, 1))
        args = argparse.Namespace(older_than_days=3, keep_last=0, dry_run=False)
        calls = []

        def fake_db_exec(sql, fetch=False):
            calls.append(sql)
            if fetch:
                return '{"research_runs": 2, "candidate_dossiers": 3, "research_stages": 4}'
            return ""

        with mock.patch.object(mod, "REPORT_ROOT", reports), \
             mock.patch.object(mod, "ensure_research_db", return_value=True), \
             mock.patch.object(mod, "db_exec", side_effect=fake_db_exec):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = mod.cmd_cleanup(args)

        self.assertEqual(rc, 0)
        out = json.loads(stdout.getvalue())
        self.assertFalse(out["dry_run"])
        self.assertEqual(len(out["deleted_paths"]), 3)
        self.assertEqual(out["pruned_db_blobs"]["research_runs"], 2)
        joined = "\n".join(calls)
        self.assertIn("row_number() OVER", joined)
        self.assertIn("PARTITION BY campaign_id", joined)
        self.assertIn("run_id NOT IN (SELECT run_id FROM ranked_runs WHERE rn <= 0)", joined)
        self.assertIn("SET summary_json = NULL, parameters_json = NULL", joined)
        self.assertIn("contract_json IS NOT NULL OR liquidity_json IS NOT NULL OR historical_pnl_json IS NOT NULL OR metrics_json IS NOT NULL", joined)
        self.assertIn("input_json IS NOT NULL OR output_json IS NOT NULL", joined)
        self.assertNotIn("SET summary_json = NULL, parameters_json = NULL, updated_at = now()", joined)
        self.assertNotIn("DELETE FROM", joined)

    def test_cleanup_keep_last_is_per_report_prefix(self):
        mod = load_script("earnings-qc-research")
        reports = pathlib.Path(tempfile.mkdtemp())
        paths = [
            ("earnings-qc-options-scan-full-old", 1),
            ("earnings-qc-options-scan-full-new", 2),
            ("research-pass-old", 3),
            ("research-pass-new", 4),
            ("qc-run-old", 5),
            ("qc-run-new", 6),
        ]
        for name, mtime in paths:
            path = reports / name
            path.mkdir()
            (path / "payload.txt").write_text("old")
            if name.startswith("research-pass-"):
                (path / "final_report.md").write_text("discard\n")
                (path / "exit_code").write_text("0\n")
            if name.startswith("qc-run-"):
                (path / "qc_run_result.json").write_text(json.dumps({"ok": True}))
            os.utime(path, (mtime, mtime))
            os.utime(path / "payload.txt", (mtime, mtime))
        args = argparse.Namespace(older_than_days=3, keep_last=1, dry_run=True)

        with mock.patch.object(mod, "REPORT_ROOT", reports), \
             mock.patch.object(mod, "ensure_research_db", return_value=False):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = mod.cmd_cleanup(args)

        self.assertEqual(rc, 0)
        deleted = {pathlib.Path(item["path"]).name for item in json.loads(stdout.getvalue())["deleted_paths"]}
        self.assertEqual(deleted, {
            "earnings-qc-options-scan-full-old",
            "research-pass-old",
            "qc-run-old",
        })

    def test_cleanup_preserves_active_expanded_run_prefixes(self):
        mod = load_script("earnings-qc-research")
        reports = pathlib.Path(tempfile.mkdtemp())
        active_pass = reports / "research-pass-active"
        active_qc = reports / "qc-run-active"
        completed_pass = reports / "research-pass-completed"
        completed_qc = reports / "qc-run-completed"
        for path in [active_pass, active_qc, completed_pass, completed_qc]:
            path.mkdir()
            (path / "payload.txt").write_text("old")
            os.utime(path, (1, 1))
            os.utime(path / "payload.txt", (1, 1))
        (completed_pass / "final_report.md").write_text("discard\n")
        (completed_pass / "exit_code").write_text("0\n")
        (completed_qc / "qc_run_result.json").write_text(json.dumps({"ok": True}))
        for path in [completed_pass, completed_qc]:
            os.utime(path, (1, 1))
        args = argparse.Namespace(older_than_days=3, keep_last=0, dry_run=True)

        with mock.patch.object(mod, "REPORT_ROOT", reports), \
             mock.patch.object(mod, "ensure_research_db", return_value=False):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = mod.cmd_cleanup(args)

        self.assertEqual(rc, 0)
        deleted = {pathlib.Path(item["path"]).name for item in json.loads(stdout.getvalue())["deleted_paths"]}
        self.assertEqual(deleted, {"research-pass-completed", "qc-run-completed"})

    def test_derive_insights_uses_research_verdict_not_only_bottleneck(self):
        mod = load_script("earnings-qc-research")
        runs = [{
            "run_id": "run-1",
            "status": "completed",
            "research_verdict": "BLOCKED_HISTORICAL_OPTION_PNL_GATE_NO_PASSING_SYMBOLS",
            "bottleneck": None,
            "final_candidate_count": 0,
            "parameters_json": {"years": 1},
        }]
        with mock.patch.object(mod, "db_history", return_value=runs):
            out = mod.derive_insights("camp", 5)
        self.assertEqual(out["bottlenecks"], {})
        self.assertEqual(out["research_verdicts"]["BLOCKED_HISTORICAL_OPTION_PNL_GATE_NO_PASSING_SYMBOLS"], 1)
        self.assertEqual(out["suggestions"][0]["action"], "try_more_years_or_stop")

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
            "chunk_count": 1,
            "forward_candidates": [{"symbol": "AAA"}],
            "final_candidates": [],
        }))
        args = mod.build_parser().parse_args(["historical", "--campaign", "camp-a", "--years", "10"])
        calls = []
        with mock.patch.object(mod, "require_research_db", return_value=True), \
             mock.patch.object(mod, "upsert_campaign", side_effect=lambda *a, **k: calls.append("campaign")), \
             mock.patch.object(mod, "upsert_run", side_effect=lambda *a, **k: calls.append("run")), \
             mock.patch.object(mod, "upsert_stage", side_effect=lambda *a, **k: calls.append("stage")), \
             mock.patch.object(mod, "run_multiyear_if_requested", return_value={"ok": True, "status": "OK_MULTIYEAR_OPTION_PNL_BACKTEST", "results": [{"symbol": "AAA", "status": "OK", "sample_size": 12, "win_rate": 0.6, "median_return_pct": 0.1, "mean_return_pct": 5.0, "leave_one_out_mean_return_pct": 1.0, "historical_event_count": 12, "dropout_pct": 0.0, "max_drawdown_pct": 10, "max_loss_pct": -20, "window_results": PASSING_WINDOWS}]}), \
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
        research = (SCRIPTS / "earnings-qc-research").read_text()
        multi = (SCRIPTS / "earnings-qc-multiyear-backtest").read_text()
        self.assertIn("scanner_failed", research)
        self.assertIn("base_scan_ok", research)
        self.assertIn("no_pass = bool(src) and bool(base_scan_ok)", research)
        self.assertIn("summary['ok'] = bool(base_scan_ok) and bool(mb.get('ok'))", research)
        self.assertNotIn("full['ok']=bool(full.get('ok')) and bool(summary.get('ok'))", multi)
        self.assertNotIn("scanner_failed", multi)

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
        workflow = (ROOT / ".github" / "workflows" / "vps-deploy.yml").read_text()
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


    def test_stage2_funnel_has_distinct_expiry_and_otm_stages(self):
        mod = load_script("earnings-qc-options-scan")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_qc_stage2_project(
            project_dir,
            [{"symbol": "OPEN", "report_date": "2026-07-15"}],
            datetime.date(2026, 7, 14),
        )
        main = (project_dir / "main.py").read_text()
        self.assertNotIn(
            '"expiry_within_0_7d_after_earnings": 0,\n            "expiry_within_0_7d_after_earnings": 0',
            main,
        )
        self.assertIn('"otm_expiry_within_0_7d_after_earnings": 0', main)
        self.assertIn(
            "'035_qc_otm_expiry_within_0_7d_after_earnings': stat_int(stats, 'trader.otm_expiry_within_0_7d_after_earnings')",
            (SCRIPTS / "earnings-qc-options-scan").read_text(),
        )
        self.assertIn(
            "'035_qc_otm_expiry_within_0_7d_after_earnings'",
            (SCRIPTS / "earnings-qc-research").read_text(),
        )

    def test_stage2_expiry_counter_can_diverge_from_otm_counter(self):
        mod = load_script("earnings-qc-options-scan")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_qc_stage2_project(
            project_dir,
            [{"symbol": "OPEN", "report_date": "2026-07-15"}],
            datetime.date(2026, 7, 14),
        )
        main = (project_dir / "main.py").read_text()

        fake_imports = types.ModuleType("AlgorithmImports")

        class QCAlgorithm:
            def debug(self, message):
                self.debug_messages.append(message)

            def set_runtime_statistic(self, key, value):
                self.runtime_statistics[key] = value

            def quit(self):
                self.quit_called = True

        fake_imports.QCAlgorithm = QCAlgorithm
        fake_imports.OptionRight = types.SimpleNamespace(CALL="call", PUT="put")
        old_imports = sys.modules.get("AlgorithmImports")
        sys.modules["AlgorithmImports"] = fake_imports
        namespace = {}
        try:
            exec(compile(main, str(project_dir / "main.py"), "exec"), namespace)
        finally:
            if old_imports is None:
                sys.modules.pop("AlgorithmImports", None)
            else:
                sys.modules["AlgorithmImports"] = old_imports

        alg = namespace["EarningsQcStage2BatchDiagnostic"]()
        alg.valuation_date = datetime.date(2026, 7, 13)
        alg.valuation_data_slice_count = 0
        alg.valuation_option_chain_slice_count = 0
        alg.option_chain_slice_count = 0
        alg.max_option_chain_slice_count = 0
        alg.option_chain_symbols_sample = []
        alg.option_by_underlying = {"OPEN": "OPEN OPTION"}
        alg.done_by_symbol = {"OPEN": False}
        alg.earnings = {"OPEN": "2026-07-15"}
        alg.rows = []
        alg.candidate_details = []
        alg.funnel = {
            "symbols_input": 1,
            "option_chain_available": 0,
            "expiry_within_0_7d_after_earnings": 0,
            "otm_expiry_within_0_7d_after_earnings": 0,
            "calls_under_max_premium": 0,
            "liquidity_pass": 0,
            "candidates": 0,
        }
        alg.securities = {"OPEN": types.SimpleNamespace(price=10.0)}
        alg.debug_messages = []
        alg.runtime_statistics = {}
        alg.quit_called = False
        alg.min_days_after_earnings = 1
        alg.max_days_after_earnings = 7
        alg.option_right = "call"
        alg.delta_min = None
        alg.delta_max = None
        alg.iv_min = None
        alg.iv_max = None
        alg.max_premium = 0.5
        alg.max_spread = None
        alg.max_spread_pct = 0.6
        alg.min_relative_spread = 0.25
        alg.vol_spread_factor = 0.5
        alg.expected_move_spread_fraction = 0.15
        alg.min_bid = 0.05
        alg.min_open_interest = 0
        alg.min_volume = 0

        contract = types.SimpleNamespace(
            symbol="OPEN 20260717 C9",
            right="call",
            expiry=datetime.datetime(2026, 7, 17),
            strike=9.0,
            bid_price=0.1,
            ask_price=0.2,
            last_price=0.2,
            open_interest=10,
            volume=5,
            greeks=types.SimpleNamespace(delta=0.4),
            implied_volatility=0.5,
        )
        chain = types.SimpleNamespace(symbol="OPEN OPTION", contracts={"c": contract})
        alg.time = datetime.datetime(2026, 7, 13, 16)
        alg.on_data(types.SimpleNamespace(option_chains={"OPEN OPTION": chain}))

        self.assertEqual(alg.funnel["option_chain_available"], 1)
        self.assertEqual(alg.funnel["expiry_within_0_7d_after_earnings"], 1)
        self.assertEqual(alg.funnel["otm_expiry_within_0_7d_after_earnings"], 0)
        self.assertEqual(alg.funnel["calls_under_max_premium"], 0)

    def test_stage2_zero_spot_records_unavailable_instead_of_selecting_all_otm(self):
        mod = load_script("earnings-qc-options-scan")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_qc_stage2_project(
            project_dir,
            [{"symbol": "OPEN", "report_date": "2026-07-15"}],
            datetime.date(2026, 7, 14),
        )
        main = (project_dir / "main.py").read_text()

        fake_imports = types.ModuleType("AlgorithmImports")

        class QCAlgorithm:
            def debug(self, message):
                self.debug_messages.append(message)

            def set_runtime_statistic(self, key, value):
                self.runtime_statistics[key] = value

            def quit(self):
                self.quit_called = True

        fake_imports.QCAlgorithm = QCAlgorithm
        fake_imports.OptionRight = types.SimpleNamespace(CALL="call", PUT="put")
        old_imports = sys.modules.get("AlgorithmImports")
        sys.modules["AlgorithmImports"] = fake_imports
        namespace = {}
        try:
            exec(compile(main, str(project_dir / "main.py"), "exec"), namespace)
        finally:
            if old_imports is None:
                sys.modules.pop("AlgorithmImports", None)
            else:
                sys.modules["AlgorithmImports"] = old_imports

        alg = namespace["EarningsQcStage2BatchDiagnostic"]()
        alg.valuation_date = datetime.date(2026, 7, 13)
        alg.valuation_data_slice_count = 0
        alg.valuation_option_chain_slice_count = 0
        alg.option_chain_slice_count = 0
        alg.max_option_chain_slice_count = 0
        alg.option_chain_symbols_sample = []
        alg.option_by_underlying = {"OPEN": "OPEN OPTION"}
        alg.done_by_symbol = {"OPEN": False}
        alg.earnings = {"OPEN": "2026-07-15"}
        alg.rows = []
        alg.candidate_details = []
        alg.funnel = {
            "symbols_input": 1,
            "option_chain_available": 0,
            "expiry_within_0_7d_after_earnings": 0,
            "otm_expiry_within_0_7d_after_earnings": 0,
            "calls_under_max_premium": 0,
            "liquidity_pass": 0,
            "candidates": 0,
        }
        alg.securities = {"OPEN": types.SimpleNamespace(price=0.0)}
        alg.debug_messages = []
        alg.runtime_statistics = {}
        alg.quit_called = False
        alg.min_days_after_earnings = 1
        alg.max_days_after_earnings = 7
        alg.option_right = "call"
        alg.delta_min = None
        alg.delta_max = None
        alg.iv_min = None
        alg.iv_max = None
        alg.max_premium = 0.5
        alg.max_spread = None
        alg.max_spread_pct = 0.6
        alg.min_relative_spread = 0.25
        alg.vol_spread_factor = 0.5
        alg.expected_move_spread_fraction = 0.15
        alg.min_bid = 0.05
        alg.min_open_interest = 0
        alg.min_volume = 0

        contract = types.SimpleNamespace(
            symbol="OPEN 20260717 C11",
            right="call",
            expiry=datetime.datetime(2026, 7, 17),
            strike=11.0,
            bid_price=0.1,
            ask_price=0.2,
            last_price=0.2,
            open_interest=10,
            volume=5,
            greeks=types.SimpleNamespace(delta=0.4),
            implied_volatility=0.5,
        )
        chain = types.SimpleNamespace(symbol="OPEN OPTION", contracts={"c": contract})
        alg.time = datetime.datetime(2026, 7, 13, 16)
        alg.on_data(types.SimpleNamespace(option_chains={"OPEN OPTION": chain}))

        self.assertEqual(alg.funnel["option_chain_available"], 1)
        self.assertEqual(alg.funnel["expiry_within_0_7d_after_earnings"], 1)
        self.assertEqual(alg.funnel["otm_expiry_within_0_7d_after_earnings"], 0)
        self.assertEqual(alg.funnel["calls_under_max_premium"], 0)
        self.assertEqual(alg.funnel["liquidity_pass"], 0)
        self.assertEqual(alg.funnel["candidates"], 0)
        self.assertEqual(alg.candidate_details, [])
        self.assertEqual(alg.rows[0]["liquidity_fail_reason_counts"], {"spot_unavailable": 1})
        self.assertEqual(alg.rows[0]["multi_year_backtest_status"], "SPOT_UNAVAILABLE")

    def test_stage2_zero_bid_uses_no_two_sided_market_not_spread_failure(self):
        mod = load_script("earnings-qc-options-scan")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_qc_stage2_project(
            project_dir,
            [{"symbol": "OPEN", "report_date": "2026-07-15"}],
            datetime.date(2026, 7, 14),
        )
        main = (project_dir / "main.py").read_text()

        fake_imports = types.ModuleType("AlgorithmImports")

        class QCAlgorithm:
            def debug(self, message):
                self.debug_messages.append(message)

            def set_runtime_statistic(self, key, value):
                self.runtime_statistics[key] = value

            def quit(self):
                self.quit_called = True

        fake_imports.QCAlgorithm = QCAlgorithm
        fake_imports.OptionRight = types.SimpleNamespace(CALL="call", PUT="put")
        old_imports = sys.modules.get("AlgorithmImports")
        sys.modules["AlgorithmImports"] = fake_imports
        namespace = {}
        try:
            exec(compile(main, str(project_dir / "main.py"), "exec"), namespace)
        finally:
            if old_imports is None:
                sys.modules.pop("AlgorithmImports", None)
            else:
                sys.modules["AlgorithmImports"] = old_imports

        alg = namespace["EarningsQcStage2BatchDiagnostic"]()
        alg.valuation_date = datetime.date(2026, 7, 13)
        alg.valuation_data_slice_count = 0
        alg.valuation_option_chain_slice_count = 0
        alg.option_chain_slice_count = 0
        alg.max_option_chain_slice_count = 0
        alg.option_chain_symbols_sample = []
        alg.option_by_underlying = {"OPEN": "OPEN OPTION"}
        alg.done_by_symbol = {"OPEN": False}
        alg.earnings = {"OPEN": "2026-07-15"}
        alg.rows = []
        alg.candidate_details = []
        alg.funnel = {
            "symbols_input": 1,
            "option_chain_available": 0,
            "expiry_within_0_7d_after_earnings": 0,
            "otm_expiry_within_0_7d_after_earnings": 0,
            "calls_under_max_premium": 0,
            "liquidity_pass": 0,
            "candidates": 0,
        }
        alg.securities = {"OPEN": types.SimpleNamespace(price=10.0)}
        alg.debug_messages = []
        alg.runtime_statistics = {}
        alg.quit_called = False
        alg.min_days_after_earnings = 1
        alg.max_days_after_earnings = 7
        alg.option_right = "call"
        alg.delta_min = None
        alg.delta_max = None
        alg.iv_min = None
        alg.iv_max = None
        alg.max_premium = 0.5
        alg.max_spread = None
        alg.max_spread_pct = 0.6
        alg.min_relative_spread = 0.25
        alg.vol_spread_factor = 0.5
        alg.expected_move_spread_fraction = 0.15
        alg.min_bid = 0.05
        alg.min_open_interest = 0
        alg.min_volume = 0

        zero_bid = types.SimpleNamespace(
            symbol="OPEN 20260717 C11",
            right="call",
            expiry=datetime.datetime(2026, 7, 17),
            strike=11.0,
            bid_price=0.0,
            ask_price=0.2,
            last_price=0.2,
            open_interest=10,
            volume=5,
            greeks=types.SimpleNamespace(delta=0.4),
            implied_volatility=0.5,
        )
        wide_spread = types.SimpleNamespace(
            symbol="OPEN 20260717 C12",
            right="call",
            expiry=datetime.datetime(2026, 7, 17),
            strike=12.0,
            bid_price=0.05,
            ask_price=0.5,
            last_price=0.5,
            open_interest=10,
            volume=5,
            greeks=types.SimpleNamespace(delta=0.4),
            implied_volatility=0.5,
        )
        chain = types.SimpleNamespace(
            symbol="OPEN OPTION",
            contracts={"zero": zero_bid, "wide": wide_spread},
        )
        alg.time = datetime.datetime(2026, 7, 13, 16)
        alg.on_data(types.SimpleNamespace(option_chains={"OPEN OPTION": chain}))

        counts = alg.rows[0]["liquidity_fail_reason_counts"]
        self.assertEqual(counts.get("no_two_sided_market"), 1)
        self.assertEqual(counts.get("spread_too_wide"), 1)
        self.assertNotIn("low_bid", counts)
        zero_bid_detail = alg.rows[0]["cheap_contract_diagnostics_sample"][0]
        self.assertEqual(zero_bid_detail["liquidity_fail_reasons"], ["no_two_sided_market"])
        self.assertIsNone(zero_bid_detail["spread"])
        self.assertIsNone(zero_bid_detail["spread_mid_pct"])


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
        self.assertIn("multiyear_json_%04d", main)
        self.assertIn("exit_reason", main)
        self.assertIn("planned_exit_date", main)
        self.assertIn("actual_exit_date", main)
        self.assertIn("exit_days_shifted", main)
        self.assertIn("liquidity_metrics", main)
        self.assertIn("expected_option_move", main)
        self.assertIn("allowed_spread", main)
        self.assertIn("self.stop_loss_max_loss_pct = None", main)
        self.assertIn('"stop_loss_trigger_count"', main)
        self.assertIn('"stop_loss_fill_variants"', main)

    def test_multiyear_generated_qc_algorithm_threads_runtime_parameters(self):
        mod = load_script("earnings-qc-multiyear-backtest")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_project(
            project_dir,
            [{
                "symbol": "OPEN",
                "earnings_date": "2026-08-04",
                "spot": 4.79,
                "contracts": [
                    {"strike": 6, "ask": 0.25},
                    {"strike": 7, "ask": 0.30},
                    {"strike": 8, "ask": 0.35},
                ],
            }],
            8,
            {
                "max_premium": 0.25,
                "entry_window": "14:35",
                "strike_range": "-20:100",
                "min_expiration_days": 5,
                "max_expiration_days": 45,
                "max_expiry_after_earnings_days": 10,
                "min_bid": 0.01,
                "max_spread": 0.35,
                "max_spread_pct": 0.7,
                "min_relative_spread": 0.2,
                "vol_spread_factor": 0.8,
                "expected_move_spread_fraction": 0.3,
                "min_open_interest": 11,
                "min_volume": 4,
                "max_contracts": 2,
                "stop_loss_max_loss_pct": -50,
                "final_min_sample_size": 8,
                "final_max_dropout_pct": 55,
                "historical_resolution": "minute",
            },
        )
        main = (project_dir / "main.py").read_text()
        self.assertIn("self.max_premium = 0.250000", main)
        self.assertIn("self.entry_min_days = 14", main)
        self.assertIn("self.entry_max_days = 35", main)
        self.assertIn("self.universe_settings.resolution = Resolution.MINUTE", main)
        self.assertIn('self.add_equity(c["symbol"], Resolution.MINUTE)', main)
        self.assertIn('self.add_option(c["symbol"], Resolution.MINUTE)', main)
        self.assertIn("strikes(-20, 100).expiration(timedelta(5), timedelta(45))", main)
        self.assertIn("if dte < 5 or dte > 45: continue", main)
        self.assertIn("self.max_days_after_earnings = 10", main)
        self.assertIn("self.min_bid = 0.010000", main)
        self.assertIn("self.max_spread = 0.350000", main)
        self.assertIn("self.max_spread_pct = 0.700000", main)
        self.assertIn("self.option_right = 'call'", main)
        self.assertIn("self.delta_target = 0.250000", main)
        self.assertIn("self.exit_days_before = 1", main)
        self.assertIn("planned_exit_date=rd-timedelta(days=self.exit_days_before)", main)
        self.assertIn("planned_exit_date=rd-timedelta(days=max(0,self.exit_days_before-1))", main)
        self.assertIn("option_right_matches", main)
        self.assertNotIn("if c.right != OptionRight.CALL: continue", main)
        self.assertIn("self.min_open_interest = 11", main)
        self.assertIn("self.min_volume = 4", main)
        self.assertIn("self.stop_loss_max_loss_pct = -50.0", main)
        self.assertIn("contract_quotes_between", main)
        self.assertIn("apply_stop_loss_variants", main)
        self.assertIn("stop_loss_same_day_trades", main)
        self.assertIn("stop_loss_next_day_trades", main)
        self.assertIn("stop_loss_mean_slippage_pct", main)
        self.assertIn("stop_loss_worst_slippage_pct", main)
        self.assertIn("stop_loss_fill_model_limitation", main)
        self.assertIn("Daily-bar stop-loss variants observe and fill from daily snapshots", main)
        self.assertIn("stop_loss_report_metrics=next_overall", main)
        self.assertIn("'same_day': dict(same_overall", main)
        self.assertIn("'next_day': dict(next_overall", main)
        self.assertIn("overall=metrics(trades,'all',8)", main)
        self.assertIn("dropout_pct<=55.000000", main)
        self.assertIn('"final_candidate_gate":{"min_sample_size":8,"max_dropout_pct":55.000000}', main)
        self.assertIn('"parameters":{"delta_target":0.250000,"exit_days_before":1,"exit_policy":', main)
        self.assertIn('"option_right":', main)
        self.assertIn("delta_targeted_comparison", main)
        self.assertIn("untraded_event_no_delta_eligible_contract_count", main)
        self.assertIn("delta_eligible=[q for q in eligible if self.delta_distance(q) is not None]", main)
        self.assertIn("windows.append(metrics(rows, str(wy)+'y', 1))", main)
        self.assertIn('"strike": 6', main)
        self.assertIn('"strike": 7', main)
        self.assertNotIn('"strike": 8', main)
        compile(main, str(project_dir / "main.py"), "exec")

    def test_multiyear_exit_days_before_changes_generated_behavior(self):
        def run(exit_days_before, report_time):
            alg = self.build_multiyear_algorithm({"exit_days_before": exit_days_before})
            alg.events["XYZ"]["2026-02-01"]["report_time"] = report_time
            quote = self.quote(0.20, ask=0.25, expiry="2026-02-05")
            self.set_multiyear_snapshots(alg, {
                "2026-01-05": quote,
                "2026-01-29": dict(quote, bid=0.25, ask=0.30, mid=0.275),
                "2026-01-31": dict(quote, bid=0.30, ask=0.35, mid=0.325),
                "2026-02-01": dict(quote, bid=0.35, ask=0.40, mid=0.375),
            })
            alg.on_end_of_algorithm()
            payload = json.loads("".join(
                alg.runtime_statistics[key]
                for key in sorted(alg.runtime_statistics)
                if key.startswith("multiyear_json_")
            ))
            return payload, payload["results"][0]["trades"][0], alg.runtime_statistics

        before_payload_1, before_trade_1, before_stats_1 = run(1, "Before Market")
        before_payload_3, before_trade_3, before_stats_3 = run(3, "Before Market")
        after_payload_1, after_trade_1, after_stats_1 = run(1, "After Market")
        after_payload_3, after_trade_3, after_stats_3 = run(3, "After Market")

        self.assertEqual(before_trade_1["planned_exit_date"], "2026-01-31")
        self.assertEqual(before_trade_3["planned_exit_date"], "2026-01-29")
        self.assertNotEqual(before_trade_1["planned_exit_date"], before_trade_3["planned_exit_date"])
        self.assertEqual(after_trade_1["planned_exit_date"], "2026-02-01")
        self.assertEqual(after_trade_3["planned_exit_date"], "2026-01-30")
        self.assertNotEqual(after_trade_1["planned_exit_date"], after_trade_3["planned_exit_date"])
        self.assertEqual(before_payload_3["parameters"]["exit_days_before"], 3)
        self.assertEqual(after_payload_3["parameters"]["exit_days_before"], 3)
        self.assertEqual(before_payload_1["exit_policy"], "sell_before_earnings_no_hold_through")
        self.assertEqual(after_payload_1["exit_policy"], "sell_before_earnings_no_hold_through")
        self.assertEqual(before_stats_1["multiyear_exit_policy"], before_payload_1["exit_policy"])
        self.assertEqual(after_stats_3["multiyear_exit_policy"], after_payload_3["exit_policy"])

    def test_multiyear_generated_qc_algorithm_defaults_resolution_to_daily(self):
        mod = load_script("earnings-qc-multiyear-backtest")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_project(
            project_dir,
            [{"symbol": "OPEN", "earnings_date": "2026-08-04", "spot": 4.79, "contracts": []}],
            8,
            {},
        )
        main = (project_dir / "main.py").read_text()
        self.assertIn("self.universe_settings.resolution = Resolution.DAILY", main)
        self.assertIn('self.add_equity(c["symbol"], Resolution.DAILY)', main)
        self.assertIn('self.add_option(c["symbol"], Resolution.DAILY)', main)
        compile(main, str(project_dir / "main.py"), "exec")

    def test_multiyear_generated_qc_algorithm_prefers_option_resolution(self):
        mod = load_script("earnings-qc-multiyear-backtest")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_project(
            project_dir,
            [{"symbol": "OPEN", "earnings_date": "2026-08-04", "spot": 4.79, "contracts": []}],
            8,
            {"historical_resolution": "daily", "option_resolution": "hour"},
        )
        main = (project_dir / "main.py").read_text()
        self.assertIn("self.universe_settings.resolution = Resolution.HOUR", main)
        self.assertIn('self.add_equity(c["symbol"], Resolution.HOUR)', main)
        self.assertIn('self.add_option(c["symbol"], Resolution.HOUR)', main)
        compile(main, str(project_dir / "main.py"), "exec")

    def test_multiyear_generated_qc_algorithm_preserves_default_dte_and_spread(self):
        mod = load_script("earnings-qc-multiyear-backtest")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_project(
            project_dir,
            [{"symbol": "OPEN", "earnings_date": "2026-08-04", "spot": 4.79, "contracts": []}],
            8,
            {},
        )
        main = (project_dir / "main.py").read_text()
        self.assertIn("strikes(-50, 300).expiration(timedelta(1), timedelta(60))", main)
        self.assertIn("if dte < 1 or dte > 60: continue", main)
        self.assertIn("self.max_spread = 0.250000", main)

    def test_multiyear_generated_qc_algorithm_defaults_to_calls_only(self):
        alg = self.build_multiyear_algorithm()
        alg.option_by_underlying = {"XYZ": "XYZ_OPT"}
        alg.securities = {"XYZ": types.SimpleNamespace(price=100.0)}
        alg.time = datetime.datetime(2026, 1, 5)
        data = types.SimpleNamespace(option_chains={
            "XYZ_OPT": [
                self.option_contract("XYZ_CALL_110", "call"),
                self.option_contract("XYZ_PUT_90", "put"),
            ]
        })

        alg.on_data(data)

        contracts = alg.snapshots["XYZ"]["2026-01-05"]["contracts"]
        self.assertEqual([c[0] for c in contracts], ["XYZ_CALL_110"])

    def test_multiyear_generated_qc_algorithm_can_snapshot_puts(self):
        alg = self.build_multiyear_algorithm({"option_right": "put"})
        alg.option_by_underlying = {"XYZ": "XYZ_OPT"}
        alg.securities = {"XYZ": types.SimpleNamespace(price=100.0)}
        alg.time = datetime.datetime(2026, 1, 5)
        data = types.SimpleNamespace(option_chains={
            "XYZ_OPT": [
                self.option_contract("XYZ_CALL_110", "call"),
                self.option_contract("XYZ_PUT_90", "put"),
            ]
        })

        alg.on_data(data)

        contracts = alg.snapshots["XYZ"]["2026-01-05"]["contracts"]
        self.assertEqual([c[0] for c in contracts], ["XYZ_PUT_90"])

    def test_multiyear_generated_qc_algorithm_treats_puts_as_otm_below_spot(self):
        alg = self.build_multiyear_algorithm({"option_right": "put"})
        put_quote = self.quote(
            0.17,
            0.20,
            symbol="XYZ_PUT_90",
            strike=90.0,
            right="put",
            delta=-0.30,
        )
        exit_quote = dict(put_quote, bid=0.30, ask=0.35, mid=0.325)
        self.set_multiyear_snapshots(alg, {
            "2026-01-05": put_quote,
            "2026-01-30": exit_quote,
        })

        alg.on_end_of_algorithm()

        payload = json.loads("".join(
            alg.runtime_statistics[key]
            for key in sorted(alg.runtime_statistics)
            if key.startswith("multiyear_json_")
        ))
        trade = payload["results"][0]["trades"][0]
        self.assertEqual(trade["contract"], "XYZ_PUT_90")
        self.assertEqual(trade["required_move_pct"], 10.0)

    def test_multiyear_generated_qc_algorithm_instruments_compact_snapshots(self):
        mod = load_script("earnings-qc-multiyear-backtest")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_project(
            project_dir,
            [{"symbol": "OPEN", "earnings_date": "2026-08-04", "spot": 4.79, "contracts": []}],
            8,
            {},
        )
        main = (project_dir / "main.py").read_text()
        self.assertIn("compact_contract", main)
        self.assertIn('"snapshot_record_format":"tuple_v1"', main)
        self.assertIn('"snapshot_contract_count"', main)
        self.assertIn('"snapshot_peak_day_count"', main)
        self.assertIn('"snapshot_strike_range":"-50:300"', main)
        self.assertIn("multiyear_snapshot_memory", main)
        self.assertIn("self.set_runtime_statistic('multiyear_'+k, str(v))", main)

    def test_multiyear_generated_qc_algorithm_reports_full_error_count_when_details_truncated(self):
        alg = self.build_multiyear_algorithm()
        event_count = 12
        alg.events = {
            "XYZ": {
                f"bad-{i:02d}": {
                    "symbol": "XYZ",
                    "report_date": f"bad-{i:02d}",
                    "report_time": "Before Market",
                }
                for i in range(event_count)
            }
        }
        alg.snapshots = {"XYZ": {}}

        alg.on_end_of_algorithm()

        payload_parts = [
            alg.runtime_statistics[key]
            for key in sorted(alg.runtime_statistics)
            if key.startswith("multiyear_json_")
        ]
        payload = json.loads("".join(payload_parts))
        self.assertEqual(payload["error_count"], event_count)
        self.assertTrue(payload["errors_truncated"])
        self.assertEqual(len(payload["errors"]), 10)
        self.assertEqual(alg.runtime_statistics["multiyear_error_count"], str(event_count))

    def test_multiyear_chunked_json_reassembles_in_order_past_99_fragments(self):
        alg = self.build_multiyear_algorithm()
        fragment_count = 150
        payload_text = json.dumps(
            {
                "type": "fragment_order_regression",
                "items": [
                    {"index": i, "value": f"{i:04d}-" + ("x" * 3475)}
                    for i in range(fragment_count)
                ],
            },
            sort_keys=True,
        )

        for i in range(0, len(payload_text), 3500):
            alg.set_runtime_statistic("multiyear_json_%04d" % (i // 3500), payload_text[i:i + 3500])

        parts = [
            alg.runtime_statistics[key]
            for key in sorted(alg.runtime_statistics)
            if key.startswith("multiyear_json_")
        ]
        self.assertGreaterEqual(len(parts), fragment_count)
        self.assertEqual(json.loads("".join(parts)), json.loads(payload_text))

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

    def test_research_result_pass_gate_rejects_bad_completed_results(self):
        mod = load_script("earnings-qc-research")
        self.assertFalse(hasattr(load_script("earnings-qc-multiyear-backtest"), "result_passes"))
        self.assertFalse(
            mod.multiyear_result_passes(
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
            mod.multiyear_result_passes(
                {
                    "status": "OK",
                    "sample_size": 12,
                    "win_rate": 0.5,
                    "median_return_pct": 10.0,
                    "mean_return_pct": 15.0,
                    "leave_one_out_mean_return_pct": 5.0,
                    "historical_event_count": 12,
                    "dropout_pct": 0.0,
                    "max_drawdown_pct": 40.0,
                    "max_loss_pct": -70.0,
                    "window_results": PASSING_WINDOWS,
                }
            )
        )

    def test_research_result_gate_reports_failed_conditions(self):
        mod = load_script("earnings-qc-research")
        out = mod.final_candidate_gate_evaluation(
            {
                "symbol": "NVDA",
                "status": "OK",
                "sample_size": 23,
                "win_rate": 0.2174,
                "mean_return_pct": 273.4,
                "leave_one_out_mean_return_pct": -39.17,
                "historical_event_count": 32,
                "dropout_pct": 28.12,
                "max_drawdown_pct": 100.0,
                "max_loss_pct": -96.15,
                "window_results": PASSING_WINDOWS,
            }
        )

        self.assertFalse(out["passed"])
        self.assertTrue(out["checks"]["sample_size_ok"])
        self.assertTrue(out["checks"]["mean_return_ok"])
        self.assertFalse(out["checks"]["win_rate_ok"])
        self.assertFalse(out["checks"]["leave_one_out_mean_return_ok"])
        self.assertFalse(out["checks"]["max_drawdown_ok"])
        self.assertFalse(out["checks"]["max_loss_ok"])
        self.assertEqual(
            out["failed_checks"],
            ["win_rate_ok", "leave_one_out_mean_return_ok", "max_drawdown_ok", "max_loss_ok"],
        )

    def test_final_gate_warns_when_sample_size_unreachable_for_years(self):
        mod = load_script("earnings-qc-research")
        warnings = mod.final_candidate_gate_warnings(1, {"min_sample_size": 12})

        self.assertEqual(warnings[0]["code"], "FINAL_SAMPLE_SIZE_UNSATISFIABLE_FOR_YEARS")
        self.assertEqual(warnings[0]["max_possible_quarterly_events"], 4)

    def test_daily_summary_does_not_surface_research_loop_broker_manifest(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        mod.STATE_DIR = tmp / "state"
        run_dir = tmp / "run"
        run_dir.mkdir()
        (run_dir / "chunk-0.stdout.json").write_text(json.dumps({
            "ok": False,
            "status": "BLOCKED_QC_BATCH_FAILED",
            "calendar_row_count": 1,
            "calendar_universe_count": 1,
            "qc_processed_row_count": 0,
            "qc_batch_count": 1,
            "candidate_details": [],
            "funnel": {},
        }))
        (run_dir / "qc_research_execution_diagnostic.json").write_text(json.dumps({
            "status": "qc_cloud_execution_failed",
            "stderr_redacted_excerpt": "Runtime Error: forced cloud failure",
            "reason": "cloud failed",
        }))
        (run_dir / "qc_research_artifact_manifest.json").write_text(json.dumps({
            "auth_status": "authenticated",
            "cloud_status": "qc_cloud_execution_failed",
            "docker_status": "not_checked",
            "execution_surface": "qc_cloud_backtest",
            "execution_rc": 1,
            "surface_attempts": [
                {"surface": "qc_cloud_backtest", "status": "qc_cloud_execution_failed", "exit_code": 1},
            ],
            "extraction_reason": "The bounded QC Cloud extract failed.",
            "artifacts": [
                {"path": "qc_research_execution_diagnostic.json", "kind": "structured_execution_diagnostic"},
            ],
        }))

        summary = mod.write_summary(run_dir, batch_size=1)
        report = (run_dir / "hebrew_report.md").read_text()

        self.assertNotIn("qc_broker_execution", summary)
        self.assertNotIn("QC broker execution", report)
        self.assertNotIn("Runtime Error: forced cloud failure", report)

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
                                "window_results": PASSING_WINDOWS,
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

    def test_full_scan_aggregation_includes_final_gate_evaluations(self):
        mod = load_script("earnings-qc-research")
        summary = mod.aggregate(
            [
                {
                    "ok": True,
                    "qc_processed_row_count": 1,
                    "calendar_row_count": 1,
                    "candidate_details": [{"symbol": "IREN", "earnings_date": "2026-08-04"}],
                    "chunk_multiyear_backtest": {
                        "ok": False,
                        "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE_NO_PASSING_SYMBOLS",
                        "results": [
                            {
                                "symbol": "IREN",
                                "status": "OK",
                                "sample_size": 5,
                                "win_rate": 0.6,
                                "mean_return_pct": 112.45,
                                "leave_one_out_mean_return_pct": 58.06,
                                "historical_event_count": 17,
                                "dropout_pct": 70.59,
                                "max_drawdown_pct": 80.0,
                                "max_loss_pct": -80.0,
                                "window_results": PASSING_WINDOWS,
                            }
                        ],
                    },
                }
            ]
        )

        evaluation = summary["final_candidate_gate_evaluations"][0]
        self.assertEqual(evaluation["symbol"], "IREN")
        self.assertEqual(evaluation["failed_checks"], ["sample_size_ok", "dropout_ok", "max_drawdown_ok"])
        self.assertEqual(evaluation["observed"]["historical_event_count"], 17)

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

    def test_research_final_candidate_gate_is_not_owned_by_multiyear_runner(self):
        mod = load_script("earnings-qc-research")
        self.assertTrue(mod.multiyear_result_passes({
            "status": "OK", "sample_size": 12, "win_rate": 0.5,
            "median_return_pct": 10.0, "mean_return_pct": 15.0,
            "leave_one_out_mean_return_pct": 5.0,
            "historical_event_count": 12, "dropout_pct": 0.0,
            "max_drawdown_pct": 40.0, "max_loss_pct": -70.0,
            "window_results": PASSING_WINDOWS,
        }))
        multi = load_script("earnings-qc-multiyear-backtest")
        self.assertFalse(hasattr(multi, "promoted_final_candidate"))
        self.assertFalse(hasattr(multi, "candidate_historical_status_blocks"))

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
            "leave_one_out_mean_return_pct": 5.0,
            "historical_event_count": 12, "dropout_pct": 0.0,
            "max_drawdown_pct": 0.0, "max_loss_pct": 0.0,
            "window_results": PASSING_WINDOWS,
        }
        self.assertTrue(full.multiyear_result_passes(row))
        self.assertFalse(hasattr(multi, "result_passes"))

    def test_multiyear_stop_loss_normalizes_positive_cli_value(self):
        multi = load_script("earnings-qc-multiyear-backtest")
        full = load_script("earnings-qc-research")
        self.assertEqual(multi.hist_params({"stop_loss_max_loss_pct": 50})["stop_loss_max_loss_pct"], -50.0)
        self.assertEqual(multi.hist_params({"stop_loss_max_loss_pct": -50})["stop_loss_max_loss_pct"], -50.0)
        args = full.build_parser().parse_args(["run", "--stop-loss-max-loss-pct", "50"])
        self.assertEqual(full.current_parameters(args)["stop_loss_max_loss_pct"], -50.0)

    def test_multiyear_exit_policy_accepts_public_alias_and_rejects_zero_days(self):
        multi = load_script("earnings-qc-multiyear-backtest")
        self.assertEqual(
            multi.hist_params({"exit_policy": "after-market-report-day-close"})["exit_policy"],
            "sell_before_earnings_no_hold_through",
        )
        self.assertEqual(
            multi.hist_params({"exit_policy": "sell_before_earnings_no_hold_through"})["exit_policy"],
            "sell_before_earnings_no_hold_through",
        )
        with self.assertRaises(SystemExit):
            multi.hist_params({"exit_days_before": 0})

    def test_multiyear_stop_loss_fill_variants_mid_window_breach(self):
        alg = self.build_multiyear_algorithm({"stop_loss_max_loss_pct": 50})
        self.set_multiyear_snapshots(alg, {
            "2026-01-06": (102.0, self.quote(0.22)),
            "2026-01-07": (108.0, self.quote(0.18)),
            "2026-01-08": (112.0, self.quote(0.14)),
        })
        trade = {
            "report_date": "2026-02-01",
            "entry_ask": 0.40,
            "contract": "XYZ_CALL_110",
            "entry_underlying": 100.0,
            "exit_underlying": 125.0,
            "realized_move_pct": 25.0,
            "return_pct": 125.0,
            "win": True,
            "exit_bid": 0.90,
        }
        variants = alg.apply_stop_loss_variants(
            "XYZ", trade, datetime.date(2026, 1, 5), datetime.date(2026, 1, 31)
        )
        self.assertEqual(variants["same_day"]["actual_exit_date"], "2026-01-07")
        self.assertEqual(variants["same_day"]["exit_bid"], 0.18)
        self.assertEqual(variants["same_day"]["exit_underlying"], 108.0)
        self.assertEqual(variants["same_day"]["realized_move_pct"], 8.0)
        self.assertEqual(variants["same_day"]["return_pct"], -55.0)
        self.assertEqual(variants["next_day"]["actual_exit_date"], "2026-01-08")
        self.assertEqual(variants["next_day"]["exit_bid"], 0.14)
        self.assertEqual(variants["next_day"]["exit_underlying"], 112.0)
        self.assertEqual(variants["next_day"]["realized_move_pct"], 12.0)
        self.assertEqual(variants["next_day"]["return_pct"], -65.0)
        self.assertEqual(variants["next_day"]["stop_loss_max_loss_pct"], -50.0)

    def test_multiyear_trade_records_entry_exit_underlying_and_realized_move(self):
        alg = self.build_multiyear_algorithm()
        self.set_multiyear_snapshots(alg, {
            "2026-01-05": (100.0, self.quote(0.39, 0.40)),
            "2026-01-31": (125.0, self.quote(0.90)),
        })
        alg.on_end_of_algorithm()
        payload = json.loads("".join(
            alg.runtime_statistics[k] for k in sorted(alg.runtime_statistics)
            if k.startswith("multiyear_json_")
        ))

        result = payload["results"][0]
        self.assertEqual(result["sample_size"], 1)
        self.assertEqual(result["median_return_pct"], 125.0)
        self.assertEqual(result["win_rate"], 1.0)
        trade = result["trades"][0]
        self.assertEqual(trade["entry_underlying"], 100.0)
        self.assertEqual(trade["exit_underlying"], 125.0)
        self.assertEqual(trade["required_move_pct"], 10.0)
        self.assertEqual(trade["realized_move_pct"], 25.0)
        self.assertAlmostEqual(
            trade["realized_move_pct"],
            (trade["exit_underlying"] / trade["entry_underlying"] - 1.0) * 100.0,
        )

    def test_multiyear_delta_targeted_comparison_keeps_baseline_trade_unchanged(self):
        alg = self.build_multiyear_algorithm({"delta_target": 0.25})
        baseline_entry = self.quote(
            0.12,
            0.13,
            symbol="XYZ_CALL_105",
            strike=105.0,
            delta=0.02,
        )
        delta_entry = self.quote(
            0.14,
            0.15,
            symbol="XYZ_CALL_115",
            strike=115.0,
            delta=0.25,
        )
        baseline_exit = dict(baseline_entry, bid=0.20, ask=0.21, mid=0.205)
        delta_exit = dict(delta_entry, bid=0.45, ask=0.46, mid=0.455)
        alg.snapshots = {
            "XYZ": {
                "2026-01-05": {"underlying": 100.0, "contracts": [baseline_entry, delta_entry]},
                "2026-01-31": {"underlying": 110.0, "contracts": [baseline_exit, delta_exit]},
            }
        }

        alg.on_end_of_algorithm()

        payload = json.loads("".join(
            alg.runtime_statistics[k] for k in sorted(alg.runtime_statistics)
            if k.startswith("multiyear_json_")
        ))
        result = payload["results"][0]
        baseline_trade = result["trades"][0]
        delta_comparison = result["delta_targeted_comparison"]
        delta_trade = delta_comparison["trades"][0]

        self.assertEqual(baseline_trade["contract"], "XYZ_CALL_105")
        self.assertEqual(baseline_trade["selection_variant"], "baseline_ask_required_move")
        self.assertEqual(result["per_trade_return_pct"], [53.85])
        self.assertEqual(delta_trade["contract"], "XYZ_CALL_115")
        self.assertEqual(delta_trade["selection_variant"], "delta_targeted")
        self.assertEqual(delta_trade["delta_target"], 0.25)
        self.assertEqual(delta_trade["delta_distance_to_target"], 0.0)
        self.assertEqual(delta_comparison["per_trade_return_pct"], [200.0])
        self.assertEqual(delta_comparison["sample_size"], 1)
        self.assertEqual(delta_comparison["dropout_pct"], 0.0)
        self.assertEqual(delta_comparison["untraded_event_no_delta_eligible_contract_count"], 0)

    def test_multiyear_delta_targeted_comparison_reports_no_delta_eligible_dropouts(self):
        alg = self.build_multiyear_algorithm()
        alg.snapshots = {
            "XYZ": {
                "2026-01-05": {
                    "underlying": 100.0,
                    "contracts": [self.quote(0.01, 0.02, symbol="XYZ_CALL_110")],
                }
            }
        }

        alg.on_end_of_algorithm()

        payload = json.loads("".join(
            alg.runtime_statistics[k] for k in sorted(alg.runtime_statistics)
            if k.startswith("multiyear_json_")
        ))
        delta_comparison = payload["results"][0]["delta_targeted_comparison"]
        self.assertEqual(delta_comparison["sample_size"], 0)
        self.assertEqual(delta_comparison["dropout_pct"], 100.0)
        self.assertEqual(delta_comparison["untraded_event_no_delta_eligible_contract_count"], 1)

    def test_multiyear_trade_records_entry_exit_iv_and_baseline_excess(self):
        alg = self.build_multiyear_algorithm()
        self.set_multiyear_snapshots(alg, {
            "2026-01-02": (100.0, self.quote(0.20, 0.21, iv=0.30) | {"symbol": "OTHER"}),
            "2026-01-05": (101.0, self.quote(0.39, 0.40, iv=0.40)),
            "2026-01-06": (102.0, self.quote(0.38, 0.39, iv=0.41) | {"symbol": "OTHER"}),
            "2026-01-07": (101.0, self.quote(0.37, 0.38, iv=0.42) | {"symbol": "OTHER"}),
            "2026-01-31": (100.0, self.quote(0.20, 0.21, iv=0.70)),
            "2026-02-02": (110.0, self.quote(0.18, 0.19, iv=0.72) | {"symbol": "OTHER"}),
        })
        alg.on_end_of_algorithm()
        payload = json.loads("".join(
            alg.runtime_statistics[k] for k in sorted(alg.runtime_statistics)
            if k.startswith("multiyear_json_")
        ))

        trade = payload["results"][0]["trades"][0]
        self.assertEqual(trade["entry_iv"], 0.40)
        self.assertEqual(trade["exit_iv"], 0.70)
        self.assertEqual(trade["iv_change_pct"], 75.0)
        self.assertEqual(trade["iv_days_to_expiry_entry"], 31)
        self.assertEqual(trade["iv_days_to_expiry_exit"], 5)
        self.assertEqual(trade["strike"], 110.0)
        self.assertEqual(trade["entry_strike_spot_ratio"], round(110.0 / 101.0, 4))
        self.assertEqual(trade["exit_strike_spot_ratio"], 1.1)
        self.assertEqual(trade["entry_delta"], 0.30)
        self.assertEqual(trade["exit_delta"], 0.30)
        self.assertIsNotNone(trade["iv_baseline_entry"])
        self.assertIsNotNone(trade["iv_excess_entry_pct"])
        self.assertIsNotNone(trade["iv_baseline_exit"])
        self.assertIsNotNone(trade["iv_excess_pct"])
        self.assertAlmostEqual(
            trade["iv_excess_change_pct"],
            trade["iv_excess_pct"] - trade["iv_excess_entry_pct"],
            places=2,
        )
        self.assertEqual(trade["iv_baseline_inputs"]["status"], "OK")
        self.assertGreater(trade["iv_baseline_inputs"]["ordinary_daily_variance_sample_size"], 0)
        self.assertEqual(trade["iv_baseline_inputs"]["earnings_jump_variance_sample_size"], 1)

    def test_multiyear_iv_baseline_uses_calendar_day_annualization(self):
        alg = self.build_multiyear_algorithm()
        annual_vol = 0.30
        daily_variance = annual_vol ** 2 / 365.0
        observed_days = [
            datetime.date(2026, 1, 2),
            datetime.date(2026, 1, 5),
            datetime.date(2026, 1, 6),
            datetime.date(2026, 1, 7),
            datetime.date(2026, 1, 8),
            datetime.date(2026, 1, 9),
            datetime.date(2026, 1, 12),
            datetime.date(2026, 1, 13),
            datetime.date(2026, 1, 14),
        ]
        prices = [100.0]
        for previous, current in zip(observed_days, observed_days[1:]):
            if current == datetime.date(2026, 1, 12):
                prices.append(prices[-1])
                continue
            gap = (current - previous).days
            prices.append(prices[-1] * math.exp(math.sqrt(daily_variance * gap)))
        alg.snapshots = {
            "XYZ": {
                day.isoformat(): {"underlying": price, "contracts": []}
                for day, price in zip(observed_days, prices)
            }
        }

        iv_inputs = alg.symbol_iv_variance_inputs(
            "XYZ",
            [{"report_date": "2026-01-09", "report_time": "AfterMarket"}],
        )

        self.assertEqual(iv_inputs["status"], "OK")
        self.assertAlmostEqual(iv_inputs["ordinary_daily_variance"], daily_variance, places=10)
        self.assertEqual(iv_inputs["earnings_jump_variance"], 0.0)
        self.assertGreater(iv_inputs["ordinary_daily_variance_sample_size"], 0)
        self.assertEqual(iv_inputs["earnings_jump_variance_sample_size"], 1)

        expiry = datetime.date(2026, 3, 1)
        for dte_exit in [4, 7, 14, 31]:
            exit_day = expiry - datetime.timedelta(days=dte_exit)
            fields = alg.iv_trade_fields(
                annual_vol,
                annual_vol,
                exit_day - datetime.timedelta(days=10),
                exit_day,
                expiry,
                iv_inputs,
            )
            self.assertEqual(fields["iv_days_to_expiry_exit"], dte_exit)
            self.assertAlmostEqual(fields["iv_baseline_entry"], annual_vol, delta=0.001)
            self.assertAlmostEqual(fields["iv_baseline_exit"], annual_vol, delta=0.001)
            self.assertAlmostEqual(fields["iv_excess_entry_pct"], 0.0, delta=0.01)
            self.assertAlmostEqual(fields["iv_excess_pct"], 0.0, delta=0.01)
            self.assertAlmostEqual(fields["iv_excess_change_pct"], 0.0, delta=0.01)

    def test_multiyear_stop_loss_next_day_final_day_fallback_uses_breach_day(self):
        alg = self.build_multiyear_algorithm({"stop_loss_max_loss_pct": 50})
        self.set_multiyear_snapshots(alg, {"2026-01-31": self.quote(0.18)})
        trade = {
            "report_date": "2026-02-01",
            "entry_ask": 0.40,
            "contract": "XYZ_CALL_110",
            "actual_exit_date": "2026-01-31",
            "exit_date": "2026-01-31",
            "exit_bid": 0.90,
            "return_pct": 125.0,
            "win": True,
        }
        variants = alg.apply_stop_loss_variants(
            "XYZ", trade, datetime.date(2026, 1, 5), datetime.date(2026, 1, 31)
        )
        self.assertTrue(variants["same_day"]["stop_loss_triggered"])
        self.assertTrue(variants["next_day"]["stop_loss_triggered"])
        self.assertEqual(variants["next_day"]["actual_exit_date"], "2026-01-31")
        self.assertEqual(variants["next_day"]["return_pct"], -55.0)

    def test_multiyear_stop_loss_no_breach_matches_unstopped_trade(self):
        alg = self.build_multiyear_algorithm({"stop_loss_max_loss_pct": 50})
        self.set_multiyear_snapshots(alg, {
            "2026-01-06": self.quote(0.25),
            "2026-01-07": self.quote(0.24),
        })
        trade = {
            "report_date": "2026-02-01",
            "entry_ask": 0.40,
            "contract": "XYZ_CALL_110",
            "actual_exit_date": "2026-01-31",
            "exit_date": "2026-01-31",
            "exit_bid": 0.90,
            "return_pct": 125.0,
            "win": True,
        }
        variants = alg.apply_stop_loss_variants(
            "XYZ", trade, datetime.date(2026, 1, 5), datetime.date(2026, 1, 31)
        )
        for name in ["same_day", "next_day"]:
            self.assertFalse(variants[name]["stop_loss_triggered"])
            self.assertEqual(variants[name]["return_pct"], trade["return_pct"])
            self.assertEqual(variants[name]["exit_bid"], trade["exit_bid"])

    def test_multiyear_stop_loss_absent_contract_defers_detection_to_next_observed_day(self):
        alg = self.build_multiyear_algorithm({"stop_loss_max_loss_pct": 50})
        alg.snapshots = {"XYZ": {
            "2026-01-06": {"underlying": 100.0, "contracts": [self.quote(0.01) | {"symbol": "OTHER"}]},
            "2026-01-07": {"underlying": 100.0, "contracts": [self.quote(0.18)]},
            "2026-01-08": {"underlying": 100.0, "contracts": [self.quote(0.16)]},
        }}
        trade = {
            "report_date": "2026-02-01",
            "entry_ask": 0.40,
            "contract": "XYZ_CALL_110",
            "return_pct": 125.0,
            "win": True,
            "exit_bid": 0.90,
        }
        variants = alg.apply_stop_loss_variants(
            "XYZ", trade, datetime.date(2026, 1, 5), datetime.date(2026, 1, 31)
        )
        self.assertEqual(variants["same_day"]["stop_loss_trigger_date"], "2026-01-07")
        self.assertEqual(variants["same_day"]["actual_exit_date"], "2026-01-07")
        self.assertEqual(variants["next_day"]["actual_exit_date"], "2026-01-08")

    def test_multiyear_stop_loss_next_day_series_drives_headline_gate(self):
        alg = self.build_multiyear_algorithm({"stop_loss_max_loss_pct": 50})
        self.set_multiyear_snapshots(alg, {
            "2026-01-05": self.quote(0.39, 0.40),
            "2026-01-06": self.quote(0.22),
            "2026-01-07": self.quote(0.18),
            "2026-01-08": self.quote(0.14),
            "2026-01-31": self.quote(0.90),
        })
        alg.on_end_of_algorithm()
        payload = json.loads("".join(
            alg.runtime_statistics[k] for k in sorted(alg.runtime_statistics)
            if k.startswith("multiyear_json_")
        ))
        self.assertEqual(payload["snapshot_memory"]["snapshot_contract_count"], 5)
        self.assertEqual(payload["snapshot_memory"]["snapshot_day_count"], 5)
        self.assertEqual(payload["snapshot_memory"]["snapshot_record_format"], "tuple_v1")
        result = payload["results"][0]
        self.assertEqual(result["per_trade_return_pct"], [-65.0])
        self.assertEqual(result["trades"][0]["stop_loss_fill_model"], "next_day")
        self.assertEqual(result["unstopped_comparison"]["per_trade_return_pct"], [125.0])
        self.assertEqual(result["stop_loss_max_loss_pct"], -50.0)
        self.assertEqual(
            result["stop_loss_fill_model_limitation"],
            "Daily-bar stop-loss variants observe and fill from daily snapshots, not true intraday stop prices, which can flatter stopped variants.",
        )

        full = load_script("earnings-qc-research")
        self.assertFalse(full.multiyear_result_passes(result))

    def test_multiyear_snapshot_memory_can_be_recovered_from_partial_runtime_stats(self):
        mod = load_script("earnings-qc-multiyear-backtest")
        stats = {
            "multiyear_snapshot_contract_count": "321",
            "multiyear_snapshot_day_count": "12",
            "multiyear_snapshot_peak_day_count": "14",
            "multiyear_snapshot_peak_contracts_per_symbol_day": "54",
            "multiyear_snapshot_record_format": "tuple_v1",
            "multiyear_snapshot_strike_range": "-50:300",
        }
        self.assertEqual(
            mod.snapshot_memory_from_runtime_stats(stats),
            {
                "snapshot_contract_count": 321,
                "snapshot_day_count": 12,
                "snapshot_peak_day_count": 14,
                "snapshot_peak_contracts_per_symbol_day": 54,
                "snapshot_record_format": "tuple_v1",
                "snapshot_strike_range": "-50:300",
            },
        )


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
        self.assertIn("liquidity_fail_reasons=\"gate_all_reasons_per_contract\"", main)
        self.assertIn("liquidity_warnings=\"zero_volume_zero_open_interest\"", main)
        self.assertIn("liquidity_fail_reason_counts", main)
        self.assertIn("liquidity_warning_counts", main)
        self.assertIn("cheap_contract_diagnostics_sample", main)
        self.assertIn("strike_spot_ratio", main)
        self.assertIn("low_bid", main)
        self.assertIn("missing_greeks", main)
        self.assertIn("missing_iv", main)
        self.assertIn("spread_too_wide", main)
        self.assertIn("zero_volume", main)
        self.assertIn("zero_open_interest", main)
        self.assertNotIn("diagnostic_zero_volume", main)
        self.assertNotIn("diagnostic_zero_open_interest", main)
        self.assertIn('"liquidity_fail_reason_counts": {}, "liquidity_warning_counts": {"zero_option_chain_slices_observed": 1}', main)
        self.assertIn("NO_QC_OPTION_CHAIN_SLICES_OBSERVED_ON_VALUATION_DATE", main)

    def test_stage2_notify_only_candidates_or_blockers(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        self.assertIn("if notify and (payload.get('candidate_count') or not payload.get('ok'))", scan)

    def test_retry_failed_uses_end_to_end_runner(self):
        full = (SCRIPTS / "earnings-qc-research").read_text()
        self.assertIn("run_chunk_end_to_end(run_dir, off, args.chunk_size, validation_years, args.end_to_end, args=args)", full)
        self.assertIn("rf.add_argument('--end-to-end'", full)
        self.assertIn("rf.add_argument('--validation-years'", full)
        self.assertIn("add_qc_parameter_args(rf, default_stage_values=False)", full)

    def test_stage2_fails_loudly_when_valuation_anchor_has_no_data(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        self.assertIn("self.valuation_data_slice_count = 0", scan)
        self.assertIn("TRADER_VALUATION_ANCHOR_NO_SESSION_DATA", scan)
        self.assertIn("trader.valuation_date", scan)

    def test_stage2_records_no_chain_rows_when_anchor_has_equity_but_no_option_chains(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        self.assertIn("self.valuation_option_chain_slice_count = 0", scan)
        self.assertNotIn("TRADER_VALUATION_ANCHOR_NO_OPTION_CHAIN_DATA", scan)
        self.assertIn("zero_option_chain_slices_observed", scan)
        self.assertIn("NO_QC_OPTION_CHAIN_SLICES_OBSERVED_ON_VALUATION_DATE", scan)
        self.assertIn("valuation_option_chain_slice_count", scan)
        self.assertIn("if current_date > self.valuation_date and self.valuation_option_chain_slice_count <= 0", scan)
        self.assertIn("self.emit_and_quit()", scan)
        self.assertIn("return", scan)
        self.assertIn("if current_date == self.valuation_date:", scan)
        self.assertIn("self.valuation_option_chain_slice_count += len(chains_by_symbol)", scan)

    def test_stage2_emits_per_symbol_no_chain_rows_when_equity_session_exists(self):
        mod = load_script("earnings-qc-options-scan")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_qc_stage2_project(
            project_dir,
            [
                {"symbol": "GEG", "report_date": "2026-08-04"},
                {"symbol": "CISS", "report_date": "2026-08-04"},
            ],
            datetime.date(2026, 7, 14),
        )
        main = (project_dir / "main.py").read_text()
        self.assertIn("self.valuation_option_chain_slice_count = 0", main)
        self.assertNotIn("TRADER_VALUATION_ANCHOR_NO_OPTION_CHAIN_DATA", main)
        self.assertIn("zero_option_chain_slices_observed", main)
        self.assertIn("trader.valuation_option_chain_slice_count", main)
        self.assertIn("current_date > self.valuation_date and self.valuation_option_chain_slice_count <= 0", main)

        fake_imports = types.ModuleType("AlgorithmImports")

        class QCAlgorithm:
            def debug(self, message):
                self.debug_messages.append(message)

            def set_runtime_statistic(self, key, value):
                self.runtime_statistics[key] = value

            def quit(self):
                self.quit_called = True

        fake_imports.QCAlgorithm = QCAlgorithm
        old_imports = sys.modules.get("AlgorithmImports")
        sys.modules["AlgorithmImports"] = fake_imports
        namespace = {}
        try:
            exec(compile(main, str(project_dir / "main.py"), "exec"), namespace)
        finally:
            if old_imports is None:
                sys.modules.pop("AlgorithmImports", None)
            else:
                sys.modules["AlgorithmImports"] = old_imports

        alg = namespace["EarningsQcStage2BatchDiagnostic"]()
        alg.valuation_date = datetime.date(2026, 7, 13)
        alg.valuation_data_slice_count = 0
        alg.valuation_option_chain_slice_count = 0
        alg.option_chain_slice_count = 0
        alg.max_option_chain_slice_count = 0
        alg.option_chain_symbols_sample = []
        alg.option_by_underlying = {"GEG": "GEG OPTION", "CISS": "CISS OPTION"}
        alg.done_by_symbol = {"GEG": False, "CISS": False}
        alg.earnings = {"GEG": "2026-08-04", "CISS": "2026-08-04"}
        alg.rows = []
        alg.candidate_details = []
        alg.funnel = {
            "symbols_input": 2,
            "option_chain_available": 0,
            "expiry_within_0_7d_after_earnings": 0,
            "calls_under_max_premium": 0,
            "liquidity_pass": 0,
            "candidates": 0,
        }
        alg.securities = {
            "GEG": types.SimpleNamespace(price=12.34),
            "CISS": types.SimpleNamespace(price=2.5),
        }
        alg.debug_messages = []
        alg.runtime_statistics = {}
        alg.quit_called = False
        alg.min_days_after_earnings = 1
        alg.max_days_after_earnings = 7
        alg.option_right = "call"
        alg.delta_min = None
        alg.delta_max = None
        alg.iv_min = None
        alg.iv_max = None
        alg.max_premium = 0.5
        alg.max_spread = None
        alg.max_spread_pct = 0.6
        alg.min_relative_spread = 0.25
        alg.vol_spread_factor = 0.5
        alg.expected_move_spread_fraction = 0.15
        alg.min_bid = 0.05
        alg.min_open_interest = 0
        alg.min_volume = 0

        empty_slice = types.SimpleNamespace(option_chains={})
        later_chain_slice = types.SimpleNamespace(
            option_chains={"NVDA": types.SimpleNamespace(symbol="NVDA OPTIONCHAIN")}
        )

        alg.time = datetime.datetime(2026, 7, 13, 16)
        alg.on_data(empty_slice)
        self.assertEqual(alg.valuation_data_slice_count, 1)
        self.assertEqual(alg.valuation_option_chain_slice_count, 0)

        alg.time = datetime.datetime(2026, 7, 14, 9, 31)
        alg.on_data(later_chain_slice)
        self.assertTrue(alg.quit_called)
        self.assertEqual([row["symbol"] for row in alg.rows], ["GEG", "CISS"])
        self.assertEqual({row["candidate_count"] for row in alg.rows}, {0})
        self.assertEqual(
            {row["multi_year_backtest_status"] for row in alg.rows},
            {"NO_QC_OPTION_CHAIN_SLICES_OBSERVED_ON_VALUATION_DATE"},
        )
        self.assertEqual(
            {tuple(row["liquidity_warning_counts"].items()) for row in alg.rows},
            {(("zero_option_chain_slices_observed", 1),)},
        )
        parsed = json.loads(alg.runtime_statistics["trader.stage2_json_0000"])
        self.assertEqual(len(parsed["rows"]), 2)
        self.assertEqual(alg.option_chain_slice_count, 0)

    def test_stage2_still_fails_loudly_when_anchor_has_zero_equity_slices(self):
        mod = load_script("earnings-qc-options-scan")
        project_dir = pathlib.Path(tempfile.mkdtemp())
        mod.write_qc_stage2_project(
            project_dir,
            [{"symbol": "OPEN", "report_date": "2026-08-04"}],
            datetime.date(2026, 7, 14),
        )
        main = (project_dir / "main.py").read_text()

        fake_imports = types.ModuleType("AlgorithmImports")

        class QCAlgorithm:
            pass

        fake_imports.QCAlgorithm = QCAlgorithm
        old_imports = sys.modules.get("AlgorithmImports")
        sys.modules["AlgorithmImports"] = fake_imports
        namespace = {}
        try:
            exec(compile(main, str(project_dir / "main.py"), "exec"), namespace)
        finally:
            if old_imports is None:
                sys.modules.pop("AlgorithmImports", None)
            else:
                sys.modules["AlgorithmImports"] = old_imports

        alg = namespace["EarningsQcStage2BatchDiagnostic"]()
        alg.valuation_date = datetime.date(2026, 7, 13)
        alg.valuation_data_slice_count = 0
        alg.valuation_option_chain_slice_count = 0
        alg.option_chain_slice_count = 0
        with self.assertRaisesRegex(Exception, "TRADER_VALUATION_ANCHOR_NO_SESSION_DATA") as ctx:
            alg.emit_and_quit()
        self.assertIn("valuation_data_slice_count=0", str(ctx.exception))

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
        self.assertIn("current_date < self.valuation_date", scan)
        self.assertIn("current_date > self.valuation_date", scan)
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

    def test_multiyear_cloud_backtest_timeout_is_configurable(self):
        mod = load_script("earnings-qc-multiyear-backtest")
        run_dir = pathlib.Path(tempfile.mkdtemp())
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return types.SimpleNamespace(stdout="", stderr="", returncode=0)

        with mock.patch.object(mod, "load_candidates", return_value=[{"symbol": "XYZ"}]), \
             mock.patch.object(mod, "write_project"), \
             mock.patch.object(mod, "ensure_project", return_value=123), \
             mock.patch.object(mod.subprocess, "run", side_effect=fake_run), \
             mock.patch.dict(os.environ, {"QC_LEAN_CLOUD_BACKTEST_TIMEOUT_SECONDS": "12"}):
            out = mod.run_backtest(run_dir, 1)

        self.assertFalse(out["ok"])
        self.assertEqual(calls[0][1]["timeout"], 180)
        self.assertEqual(calls[1][0][:3], ["lean", "cloud", "backtest"])
        self.assertEqual(calls[1][1]["timeout"], 12)

    def test_full_scan_gate_rejects_failed_window_results(self):
        full = load_script("earnings-qc-research")
        row = {
            "status": "OK", "sample_size": 12, "win_rate": 0.5,
            "median_return_pct": 10.0, "mean_return_pct": 15.0,
            "leave_one_out_mean_return_pct": 5.0,
            "historical_event_count": 12, "dropout_pct": 0.0,
            "max_drawdown_pct": 0.0, "max_loss_pct": 0.0,
            "window_results": [
                {"window": "1y", "status": "BLOCKED_HISTORICAL_OPTION_SAMPLE_INSUFFICIENT", "sample_size": 0},
                {"window": "3y", "status": "OK", "sample_size": 3},
            ],
        }
        self.assertFalse(full.multiyear_result_passes(row))

    def test_full_scan_gate_rejects_missing_leave_one_out_or_high_dropout(self):
        full = load_script("earnings-qc-research")
        base = {
            "status": "OK", "sample_size": 12, "win_rate": 0.5,
            "median_return_pct": -20.0, "mean_return_pct": 15.0,
            "max_drawdown_pct": 0.0, "max_loss_pct": 0.0,
            "historical_event_count": 12, "dropout_pct": 0.0,
            "window_results": PASSING_WINDOWS,
        }
        self.assertFalse(full.multiyear_result_passes(dict(base)))
        self.assertFalse(full.multiyear_result_passes(dict(base, leave_one_out_mean_return_pct=5.0, historical_event_count=22, dropout_pct=45.5)))
        self.assertTrue(full.multiyear_result_passes(dict(base, leave_one_out_mean_return_pct=5.0)))

    def test_full_scan_gate_rejects_missing_window_results(self):
        full = load_script("earnings-qc-research")
        row = {
            "status": "OK", "sample_size": 12, "win_rate": 0.5,
            "median_return_pct": 10.0, "mean_return_pct": 15.0,
            "leave_one_out_mean_return_pct": 5.0,
            "historical_event_count": 12, "dropout_pct": 0.0,
            "max_drawdown_pct": 0.0, "max_loss_pct": 0.0,
        }
        self.assertFalse(full.multiyear_result_passes(row))

    def test_multiyear_backtest_persists_trade_arrays_and_dropout_fields(self):
        multi = (SCRIPTS / "earnings-qc-multiyear-backtest").read_text()
        self.assertIn("per_trade_return_pct", multi)
        self.assertIn("leave_one_out_mean_return_pct", multi)
        self.assertIn("dropout_pct", multi)
        self.assertIn('"trades":trades', multi)

    def test_stage2_blocks_zero_processed_rows_on_valuation_date(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        self.assertIn("latest_weekday_on_or_before", scan)
        self.assertIn("BLOCKED_QC_NO_OPTION_CHAIN_ROWS_ON_VALUATION_DATE", scan)
        self.assertIn("valuation_date", scan)

    def test_stage2_runner_parses_chunked_stage2_json(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        self.assertIn("trader.stage2_json_%04d", scan)
        self.assertIn("out['parsed_result'] = json.loads(''.join(parts))", scan)
        self.assertIn('"candidate_details": self.candidate_details', scan)

    def test_stage2_chunked_json_reassembles_in_order_past_99_fragments(self):
        fragment_count = 150
        payload = {
            "type": "earnings_qc_stage2_batch_diagnostic",
            "rows": [
                {"symbol": f"S{i:04d}", "diagnostic": "x" * 3475}
                for i in range(fragment_count)
            ],
        }
        payload_text = json.dumps(payload, sort_keys=True)
        stats = {
            "trader.stage2_json_%04d" % (i // 3500): payload_text[i:i + 3500]
            for i in range(0, len(payload_text), 3500)
        }

        parts = [stats[key] for key in sorted(stats) if key.startswith("trader.stage2_json_")]

        self.assertGreaterEqual(len(parts), fragment_count)
        self.assertEqual(json.loads("".join(parts)), payload)

    def test_qc_cloud_extract_uses_four_digit_chunk_keys(self):
        script = (ROOT / "agent-platform" / "scripts" / "trading-research-qc-cloud-extract").read_text()
        self.assertIn("trader.qc_extract_json_%04d", script)
        self.assertNotIn("trader.qc_extract_json_%03d", script)

    def test_run_now_uses_chunked_stage2_candidate_details_before_capped_stat(self):
        mod = load_script("earnings-qc-options-scan")
        old_root = mod.REPORT_ROOT
        mod.REPORT_ROOT = pathlib.Path(tempfile.mkdtemp())
        bulky_contract = {
            "contract": "OPEN 260807C00010000",
            "expiry": "2026-08-07",
            "dte": 37,
            "days_after_earnings": 3,
            "strike": 10.0,
            "ask": 0.25,
            "bid": 0.2,
            "diagnostic": "x" * 1800,
        }
        candidate_details = [
            {"symbol": symbol, "earnings_date": "2026-08-04", "contracts": [bulky_contract]}
            for symbol in ["AAA", "BBB", "CCC"]
        ]
        truncated_legacy_json = json.dumps(candidate_details, sort_keys=True)[:3900]
        calendar_rows = [{"symbol": c["symbol"], "report_date": c["earnings_date"]} for c in candidate_details]

        mod.nasdaq_calendar_window = lambda start, end: (calendar_rows, [{"start": start.isoformat(), "end": end.isoformat()}])
        mod.qc_capability_probe = lambda *a, **k: {
            "qc_option_chain_batch_diagnostic": {
                "ok": True,
                "runtime_statistics": {
                    "trader.candidates": "3",
                    "trader.candidates_json": truncated_legacy_json,
                    "trader.symbols_input": "3",
                },
                "symbols_requested": 3,
                "parsed_result": {
                    "rows": [{"symbol": c["symbol"]} for c in candidate_details],
                    "candidate_details": candidate_details,
                },
            }
        }
        try:
            rc = mod.run_now(notify=False, qc_batch_limit=3, as_of_date="2026-07-01")
            result_path = next(mod.REPORT_ROOT.glob("*/result.json"))
            result = json.loads(result_path.read_text())
        finally:
            mod.REPORT_ROOT = old_root

        self.assertEqual(rc, 0)
        self.assertTrue(result["ok"])
        self.assertFalse(result["candidate_details_parse_failed"])
        self.assertEqual(result["candidate_count"], 3)
        self.assertEqual([c["symbol"] for c in result["candidate_details"]], ["AAA", "BBB", "CCC"])

    def test_stage2_reports_qc_capacity_without_exposing_cli_output(self):
        scan = (SCRIPTS / "earnings-qc-options-scan").read_text()
        helper = (SCRIPTS / "qc_cloud_capacity.py").read_text()
        self.assertIn("BLOCKED_QC_CLOUD_NO_SPARE_NODES", scan)
        self.assertIn("capacity_blocked", scan)
        self.assertIn("classify_qc_cloud_capacity", scan)
        self.assertIn("error_class", helper)
        self.assertIn("no spare nodes available", helper)
        self.assertNotIn("'backtest_stdout':", scan)
        self.assertNotIn("'backtest_stderr':", scan)

    def test_stage2_classifies_qc_cloud_rate_limit_from_shared_helper(self):
        mod = load_script("earnings-qc-options-scan")
        tmp = pathlib.Path(tempfile.mkdtemp())
        old_workspace = mod.LEAN_WORKSPACE
        mod.LEAN_WORKSPACE = tmp / "lean"
        mod.LEAN_WORKSPACE.mkdir()
        rows = [{"symbol": "AAA", "report_date": "2026-08-01"}]
        calls = [
            subprocess.CompletedProcess(["lean", "cloud", "push"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["lean", "cloud", "backtest"], 1, stdout="", stderr="Too many backtest requests; try again later."),
        ]
        try:
            with mock.patch.object(mod, "ensure_qc_project", return_value=(123, "org")), \
                 mock.patch.object(mod.subprocess, "run", side_effect=calls), \
                 mock.patch.dict(os.environ, {"QC_STAGE2_BACKTEST_ATTEMPTS": "1"}):
                out = mod.run_qc_stage2_batch(rows, tmp, 1, datetime.date(2026, 7, 1))
        finally:
            mod.LEAN_WORKSPACE = old_workspace
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "BLOCKED_QC_CLOUD_RATE_LIMITED")
        self.assertTrue(out["rate_limited"])
        self.assertEqual(out["error_class"], "qc_cloud_rate_limit")

    def test_multiyear_reports_qc_capacity_without_strategy_gate_status(self):
        mod = load_script("earnings-qc-multiyear-backtest")
        tmp = pathlib.Path(tempfile.mkdtemp())
        run_dir = tmp / "run"
        run_dir.mkdir()
        (run_dir / "full_summary.json").write_text(json.dumps({
            "forward_candidates": [{"symbol": "WMT", "earnings_date": "2026-08-21", "contracts": []}]
        }))
        old_workspace = mod.LEAN_WORKSPACE
        mod.LEAN_WORKSPACE = tmp / "lean"
        mod.LEAN_WORKSPACE.mkdir()
        calls = [
            subprocess.CompletedProcess(["lean", "cloud", "push"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["lean", "cloud", "backtest"], 1, stdout="", stderr="There are no spare nodes available in your cluster."),
        ]
        try:
            with mock.patch.object(mod, "ensure_project", return_value=456), \
                 mock.patch.object(mod.subprocess, "run", side_effect=calls):
                out = mod.run_backtest(run_dir, 10)
        finally:
            mod.LEAN_WORKSPACE = old_workspace
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "BLOCKED_QC_CLOUD_NO_SPARE_NODES")
        self.assertNotEqual(out["status"], "BLOCKED_MULTIYEAR_OPTION_PNL_BACKTEST")
        self.assertTrue(out["capacity_blocked"])

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

    def test_cmd_run_uses_validation_years_for_historical_runner(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        calls = []
        mod.STATE_DIR = tmp / "state"
        mod.require_research_db = lambda: True
        mod.upsert_campaign = lambda *a, **k: None
        mod.upsert_run = lambda *a, **k: None
        mod.latest_db_run = lambda campaign: {"run_id": "rid", "run_dir": str(tmp)}
        mod.discover_calendar_total = lambda run_dir, batch_size, start_offset, validation_years, end_to_end, symbols, args=None: calls.append(("discover", validation_years)) or 1
        mod.run_chunks_parallel = lambda run_dir, offsets, batch_size, parallel, validation_years, end_to_end, symbols, args=None: calls.append(("chunks", validation_years))
        mod.write_summary = lambda run_dir, batch_size, notify=False: {"ok": True, "status": "OK_FULL_QC_SCAN"}
        mod.persist_summary_to_db = lambda campaign_id, run_id, run_dir, summary, params: calls.append(("params", params.get("validation_years")))
        mod.run_multiyear_if_requested = lambda *a, **k: None
        args = mod.build_parser().parse_args(["run", "--run-dir", str(tmp), "--run-id", "rid", "--years", "1", "--validation-years", "10", "--no-outbox"])
        rc = mod.cmd_run(args)
        self.assertEqual(rc, 0)
        self.assertIn(("discover", 10), calls)
        self.assertIn(("chunks", 10), calls)
        self.assertIn(("params", 10), calls)

    def test_run_multiyear_if_requested_persists_timeout_object(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        runner = tmp / "earnings-qc-multiyear-backtest"
        runner.write_text("#!/usr/bin/env bash\n")
        runner.chmod(0o755)
        mod.MULTIYEAR = runner
        args = types.SimpleNamespace(
            end_to_end=True,
            years=1,
            validation_years=10,
            entry_window=None,
            exit_days_before=None,
            exit_policy=None,
            historical_resolution=None,
            max_contracts=None,
            path_metrics=None,
        )
        exc = subprocess.TimeoutExpired(["multiyear"], 7, output="stdout text", stderr="stderr text")
        with mock.patch.dict(os.environ, {"QC_MULTIYEAR_TIMEOUT_SECONDS": "7"}), \
             mock.patch.object(mod.subprocess, "run", side_effect=exc):
            out = mod.run_multiyear_if_requested(tmp, args)
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "BLOCKED_MULTIYEAR_TIMEOUT")
        self.assertEqual(out["blocked_reason"], "multiyear runner timed out after 7s")
        self.assertIsNone(out["returncode"])
        self.assertEqual((tmp / "multiyear_runner.stdout.json").read_text(), "stdout text")
        self.assertEqual((tmp / "multiyear_runner.stderr.log").read_text(), "stderr text")


    def test_cmd_run_allows_put_or_both_for_historical_after_option_right_forwarding(self):
        mod = load_script("earnings-qc-research")
        for right in ["put", "both"]:
            mod.require_research_db = mock.Mock(return_value=False)
            args = mod.build_parser().parse_args(["run", "--option-right", right, "--end-to-end"])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = mod.cmd_run(args)
            self.assertEqual(rc, 1)
            self.assertIn("DB_UNAVAILABLE", buf.getvalue())
            mod.require_research_db.assert_called_once()

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
        args = argparse.Namespace(entry_window="14:28", exit_days_before="2", exit_policy="before-earnings", historical_resolution="minute", option_resolution="hour", option_right="put", delta_target=0.25, max_contracts=3, path_metrics="intraday", max_premium=0.25, min_bid=0.01, max_spread=0.35, max_spread_pct=0.7, min_relative_spread=0.2, vol_spread_factor=0.8, expected_move_spread_fraction=0.3, min_open_interest=11, min_volume=4, strike_range="-20:100", min_expiration_days=5, max_expiration_days=45, max_expiry_after_earnings_days=10, stop_loss_max_loss_pct=-50)
        out = mod.run_chunk_multiyear(tmp, chunk, years=9, args=args)
        argv = out["argv"]
        self.assertIn("--entry-window", argv)
        self.assertIn("14:28", argv)
        self.assertIn("--historical-resolution", argv)
        self.assertIn("minute", argv)
        self.assertIn("--option-resolution", argv)
        self.assertIn("hour", argv)
        self.assertIn("--option-right", argv)
        self.assertIn("put", argv)
        self.assertIn("--delta-target", argv)
        self.assertIn("0.25", argv)
        self.assertIn("--max-contracts", argv)
        self.assertIn("3", argv)
        self.assertIn("--max-premium", argv)
        self.assertIn("0.25", argv)
        self.assertIn("--max-spread", argv)
        self.assertIn("0.35", argv)
        self.assertIn("--strike-range", argv)
        self.assertIn("-20:100", argv)
        self.assertIn("--max-expiration-days", argv)
        self.assertIn("45", argv)
        self.assertIn("--stop-loss-max-loss-pct", argv)
        self.assertIn("-50", argv)

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

    def test_research_cli_historical_accepts_qc_gate_params(self):
        mod = load_script("earnings-qc-research")
        args = mod.build_parser().parse_args([
            "historical",
            "--run-dir", "/tmp/example-run",
            "--years", "10",
            "--end-to-end",
            "--max-premium", "1.50",
            "--max-spread", "0.75",
            "--max-spread-pct", "0.70",
            "--min-open-interest", "10",
            "--min-volume", "5",
        ])
        params = mod.current_parameters(args)
        self.assertEqual(params["max_premium"], 1.50)
        self.assertEqual(params["max_spread"], 0.75)
        self.assertEqual(params["max_spread_pct"], 0.70)
        self.assertEqual(params["min_open_interest"], 10)
        self.assertEqual(params["min_volume"], 5)

    def test_research_cli_historical_does_not_forward_qc_defaults(self):
        mod = load_script("earnings-qc-research")
        args = mod.build_parser().parse_args([
            "historical",
            "--run-dir", "/tmp/example-run",
            "--years", "10",
            "--end-to-end",
        ])
        params = mod.current_parameters(args)
        for key in [
            "calendar_from_days",
            "calendar_to_days",
            "calendar_source",
            "qc_resolution",
            "min_expiry_after_earnings_days",
            "max_expiry_after_earnings_days",
            "min_expiration_days",
            "max_expiration_days",
            "strike_range",
            "option_right",
            "max_premium",
            "max_spread",
            "max_spread_pct",
        ]:
            self.assertNotIn(key, params)

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
        self.assertIn("strikes(-50, 300).expiration(0, 120)", main)
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
            "chunk_count": 1,
            "failed_chunks": [{"status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE"}],
            "failed_chunk_count": 1,
            "aggregate_funnel": {},
            "forward_candidates": [{"symbol": "TE"}],
            "final_candidates": [],
        }))
        mb = {"ok": False, "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE_NO_PASSING_SYMBOLS", "results": [{"symbol": "TE", "sample_size": 4, "window_results": PASSING_WINDOWS}]}
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
            "chunk_multiyear_backtest": {"ok": False, "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE_NO_PASSING_SYMBOLS", "results": [{"symbol": "TE", "window_results": PASSING_WINDOWS}]},
        }
        out = mod.aggregate([chunk])
        self.assertEqual(out["status"], "NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL")
        self.assertEqual(out["failed_chunk_count"], 0)
        self.assertTrue(out["historical_gate_ran"])
        self.assertTrue(out["historical_gate_no_pass"])
        self.assertFalse(out["historical_gate_blocked"])
        self.assertFalse(out["multiyear_failed"])

    def test_chunked_aggregate_missing_window_evidence_blocks_no_pass(self):
        mod = load_script("earnings-qc-research")
        for result in [{"symbol": "TE"}, {"symbol": "TE", "window_results": []}]:
            chunk = {
                "ok": True,
                "calendar_row_count": 1,
                "calendar_universe_count": 1,
                "qc_processed_row_count": 1,
                "candidate_details": [{"symbol": "TE", "earnings_date": "2026-08-01"}],
                "funnel": {},
                "chunk_multiyear_backtest": {"ok": True, "status": "OK_MULTIYEAR_OPTION_PNL_BACKTEST", "results": [result]},
            }
            out = mod.aggregate([chunk])
            self.assertEqual(out["status"], "BLOCKED_HISTORICAL_OPTION_PNL_MISSING_WINDOW_EVIDENCE")
            self.assertFalse(out["historical_gate_no_pass"])
            self.assertTrue(out["historical_gate_blocked"])
            self.assertNotEqual(out["status"], "NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL")

    def test_refresh_summary_missing_window_evidence_blocks_no_pass(self):
        mod = load_script("earnings-qc-research")
        for result in [{"symbol": "TE"}, {"symbol": "TE", "window_results": []}]:
            tmp = pathlib.Path(tempfile.mkdtemp())
            (tmp / "full_summary.json").write_text(json.dumps({
                "ok": False,
                "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE",
                "calendar_row_count": 1,
                "calendar_universe_count": 1,
                "qc_symbols_scanned": 1,
                "chunk_count": 1,
                "failed_chunks": [],
                "failed_chunk_count": 0,
                "aggregate_funnel": {},
                "forward_candidates": [{"symbol": "TE"}],
                "final_candidates": [],
            }))
            mb = {"ok": True, "status": "OK_MULTIYEAR_OPTION_PNL_BACKTEST", "results": [result]}
            out = mod.refresh_summary_after_historical(tmp, mb)
            self.assertEqual(out["status"], "BLOCKED_HISTORICAL_OPTION_PNL_MISSING_WINDOW_EVIDENCE")
            self.assertFalse(out["historical_gate_no_pass"])
            self.assertTrue(out["historical_gate_blocked"])
            self.assertNotEqual(out["status"], "NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL")

    def test_refresh_summary_no_forward_candidates_is_not_multiyear_infra_failure(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "full_summary.json").write_text(json.dumps({
            "ok": False,
            "status": "NO_FORWARD_CANDIDATES",
            "calendar_row_count": 2,
            "calendar_universe_count": 2,
            "qc_symbols_scanned": 2,
            "chunk_count": 1,
            "failed_chunks": [],
            "failed_chunk_count": 0,
            "aggregate_funnel": {},
            "forward_candidates": [],
            "final_candidates": [],
        }))
        mb = {"ok": False, "status": "NO_FORWARD_CANDIDATES", "results": []}
        out = mod.refresh_summary_after_historical(tmp, mb)
        self.assertEqual(out["status"], "NO_FORWARD_CANDIDATES")
        self.assertTrue(out["ok"])
        self.assertFalse(out["historical_gate_blocked"])
        self.assertFalse(out["multiyear_failed"])
        self.assertEqual(out["failed_chunk_count"], 0)

    def test_refresh_summary_empty_run_dir_does_not_become_no_forward_success(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "full_summary.json").write_text(json.dumps({
            "ok": False,
            "status": "BLOCKED_FULL_SCAN_NOT_RUN",
            "calendar_row_count": 0,
            "calendar_universe_count": 0,
            "qc_symbols_scanned": 0,
            "chunk_count": 0,
            "failed_chunks": [],
            "failed_chunk_count": 0,
            "aggregate_funnel": {},
            "forward_candidates": [],
            "final_candidates": [],
        }))
        mb = {"ok": False, "status": "NO_FORWARD_CANDIDATES", "results": []}
        out = mod.refresh_summary_after_historical(tmp, mb)
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "BLOCKED_FULL_SCAN_NOT_RUN")
        self.assertFalse(out["historical_gate_blocked"])
        self.assertFalse(out["multiyear_failed"])

    def test_refresh_summary_no_forward_candidates_does_not_hide_missing_runner(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "full_summary.json").write_text(json.dumps({
            "ok": True,
            "status": "OK_FULL_QC_SCAN",
            "calendar_row_count": 2,
            "calendar_universe_count": 2,
            "qc_symbols_scanned": 2,
            "chunk_count": 1,
            "failed_chunks": [],
            "failed_chunk_count": 0,
            "aggregate_funnel": {},
            "forward_candidates": [],
            "final_candidates": [],
        }))
        mb = {"ok": False, "status": "BLOCKED_MULTIYEAR_RUNNER_MISSING", "results": []}
        out = mod.refresh_summary_after_historical(tmp, mb)
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "BLOCKED_MULTIYEAR_RUNNER_MISSING")
        self.assertTrue(out["multiyear_failed"])
        self.assertEqual(out["failed_chunk_count"], 0)

    def test_refresh_summary_no_forward_candidates_preserves_partial_scan_status(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "full_summary.json").write_text(json.dumps({
            "ok": False,
            "status": "PARTIAL_FULL_QC_SCAN",
            "calendar_row_count": 2,
            "calendar_universe_count": 2,
            "qc_symbols_scanned": 1,
            "chunk_count": 1,
            "failed_chunks": [{"status": "BLOCKED_QC_BATCH_FAILED", "blocked_reason": "QC batch failed"}],
            "failed_chunk_count": 1,
            "aggregate_funnel": {},
            "forward_candidates": [],
            "final_candidates": [],
        }))
        mb = {"ok": False, "status": "NO_FORWARD_CANDIDATES", "results": []}
        out = mod.refresh_summary_after_historical(tmp, mb)
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "PARTIAL_FULL_QC_SCAN")
        self.assertEqual(out["failed_chunk_count"], 1)
        self.assertFalse(out["multiyear_failed"])

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

    def test_chunked_final_candidates_reject_blocked_candidate_status(self):
        mod = load_script("earnings-qc-research")
        blocked_symbols = ["SPCE", "SUNDAY2", "SUNDAY3"]
        out = mod.aggregate([{
            "ok": True,
            "calendar_row_count": 3,
            "calendar_universe_count": 3,
            "qc_processed_row_count": 3,
            "candidate_details": [{
                "symbol": symbol,
                "earnings_date": "2026-08-01",
                "historical_backtest_status": "BLOCKED_HISTORICAL_EARNINGS_DATES_NOT_READY",
            } for symbol in blocked_symbols],
            "funnel": {},
            "chunk_multiyear_backtest": {
                "ok": True,
                "status": "OK_MULTIYEAR_OPTION_PNL_BACKTEST",
                "results": [{
                    "symbol": symbol,
                    "status": "OK",
                    "sample_size": 12,
                    "win_rate": 0.8,
                    "median_return_pct": 0.1,
                    "mean_return_pct": 0.1,
                    "max_drawdown_pct": 10,
                    "max_loss_pct": -20,
                } for symbol in blocked_symbols],
            },
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
            "chunk_count": 1,
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
            "chunk_count": 1,
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

    def test_refresh_summary_rejects_blocked_candidate_status(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "full_summary.json").write_text(json.dumps({
            "ok": False,
            "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE",
            "calendar_row_count": 1,
            "calendar_universe_count": 1,
            "qc_symbols_scanned": 1,
            "chunk_count": 1,
            "failed_chunks": [],
            "failed_chunk_count": 0,
            "aggregate_funnel": {},
            "forward_candidates": [{
                "symbol": "TE",
                "earnings_date": "2026-08-01",
                "historical_backtest_status": "BLOCKED_HISTORICAL_EARNINGS_DATES_NOT_READY",
            }],
            "final_candidates": [],
        }))
        mb = {
            "ok": True,
            "status": "OK_MULTIYEAR_OPTION_PNL_BACKTEST",
            "results": [{
                "symbol": "TE",
                "status": "OK",
                "sample_size": 12,
                "win_rate": 0.8,
                "median_return_pct": 0.1,
                "mean_return_pct": 0.1,
                "max_drawdown_pct": 10,
                "max_loss_pct": -20,
            }],
        }
        out = mod.refresh_summary_after_historical(tmp, mb)
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "BLOCKED_HISTORICAL_OPTION_PNL_GATE")
        self.assertTrue(out["historical_gate_blocked"])
        self.assertEqual(out["final_candidate_count"], 0)

    def test_refresh_summary_honors_final_gate_env_overrides(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "full_summary.json").write_text(json.dumps({
            "ok": False,
            "status": "BLOCKED_HISTORICAL_OPTION_PNL_GATE",
            "calendar_row_count": 1,
            "calendar_universe_count": 1,
            "qc_symbols_scanned": 1,
            "chunk_count": 1,
            "failed_chunks": [],
            "failed_chunk_count": 0,
            "aggregate_funnel": {},
            "forward_candidates": [{"symbol": "TE", "earnings_date": "2026-08-01"}],
            "final_candidates": [],
        }))
        mb = {
            "ok": True,
            "status": "OK_MULTIYEAR_OPTION_PNL_BACKTEST",
            "results": [{
                "symbol": "TE",
                "status": "OK",
                "sample_size": 12,
                "win_rate": 0.8,
                "median_return_pct": 0.1,
                "mean_return_pct": 0.1,
                "leave_one_out_mean_return_pct": 0.1,
                "historical_event_count": 12,
                "dropout_pct": 0.0,
                "max_drawdown_pct": 10,
                "max_loss_pct": -20,
                "window_results": PASSING_WINDOWS,
            }],
        }
        with mock.patch.dict(os.environ, {"QC_FINAL_MIN_WIN_RATE": "0.99"}):
            out = mod.refresh_summary_after_historical(tmp, mb)
        self.assertFalse(out["ok"])
        self.assertEqual(out["final_candidate_count"], 0)
        self.assertEqual(out["status"], "NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL")

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
            "chunk_count": 1,
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

    def test_serial_chunk_runner_records_exceptions_and_continues(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        calls = []

        def fake_run_chunk_end_to_end(run_dir, offset, *args, **kwargs):
            calls.append(offset)
            if offset == 10:
                raise RuntimeError("boom")
            return {"ok": True, "_chunk_offset": offset}

        with mock.patch.object(mod, "run_chunk_end_to_end", fake_run_chunk_end_to_end), mock.patch.dict(os.environ, {"QC_FULL_CHUNK_DELAY_SECONDS": "0"}):
            mod.run_chunks_parallel(tmp, [10, 20], 5, 1, 10, True)

        self.assertEqual(calls, [10, 20])
        written = json.loads((tmp / "chunk-10.stdout.json").read_text())
        self.assertEqual(written["status"], "BLOCKED_CHUNK_EXCEPTION")
        self.assertIn("boom", written["blocked_reason"])

    def test_retry_failed_includes_capacity_blocked_offsets(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        retried = []
        forwarded_args = []
        summaries = [{
            "failed_chunks": [],
            "historical_failed_chunks": [],
            "qc_capacity_blocked_chunks": [{"offset": 25, "status": "BLOCKED_QC_CLOUD_NO_SPARE_NODES"}],
        }]

        args = types.SimpleNamespace(
            campaign="camp-a",
            run_id="run-a",
            run_dir=str(tmp),
            offset=None,
            validation_years=10,
            years=1,
            chunk_size=5,
            end_to_end=True,
            notify=False,
            option_right="put",
        )
        def fake_run_chunk_end_to_end(*a, **k):
            retried.append(a[1])
            forwarded_args.append(k.get("args"))

        with mock.patch.object(mod, "require_research_db", return_value=True), mock.patch.object(mod, "latest_db_run", return_value={"run_id": "run-a", "run_dir": str(tmp)}), mock.patch.object(mod, "aggregate", side_effect=summaries), mock.patch.object(mod, "load_chunks", return_value=[]), mock.patch.object(mod, "run_chunk_end_to_end", side_effect=fake_run_chunk_end_to_end), mock.patch.object(mod, "write_summary", return_value={"ok": True, "status": "OK_FULL_QC_SCAN"}), mock.patch.object(mod, "persist_summary_to_db"):
            rc = mod.cmd_retry_failed(args)

        self.assertEqual(rc, 0)
        self.assertEqual(retried, [25])
        self.assertEqual([a.option_right for a in forwarded_args], ["put"])

    def test_retry_failed_persists_rewritten_summary_to_db(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        summaries = [{
            "failed_chunks": [{"offset": 10}],
            "historical_failed_chunks": [],
            "qc_capacity_blocked_chunks": [],
        }]
        rewritten = {
            "ok": True,
            "status": "OK_FULL_QC_SCAN",
            "final_candidates": [{"symbol": "AAA"}],
            "final_candidate_count": 1,
        }
        persisted = []
        args = mod.build_parser().parse_args([
            "retry-failed",
            "--campaign", "camp-a",
            "--run-dir", str(tmp),
            "--run-id", "run-a",
            "--chunk-size", "5",
            "--years", "1",
            "--validation-years", "10",
        ])

        with mock.patch.object(mod, "require_research_db", return_value=True), \
             mock.patch.object(mod, "latest_db_run", return_value={"run_id": "run-a", "run_dir": str(tmp)}), \
             mock.patch.object(mod, "aggregate", side_effect=summaries), \
             mock.patch.object(mod, "load_chunks", return_value=[]), \
             mock.patch.object(mod, "run_chunk_end_to_end"), \
             mock.patch.object(mod, "write_summary", return_value=rewritten.copy()), \
             mock.patch.object(mod, "persist_summary_to_db", side_effect=lambda *a, **k: persisted.append(a)):
            rc = mod.cmd_retry_failed(args)

        self.assertEqual(rc, 0)
        self.assertEqual(len(persisted), 1)
        campaign_id, run_id, run_dir, summary, params = persisted[0]
        self.assertEqual(campaign_id, "camp-a")
        self.assertEqual(run_id, "run-a")
        self.assertEqual(run_dir, tmp)
        self.assertEqual(summary["run_id"], "run-a")
        self.assertEqual(summary["campaign_id"], "camp-a")
        self.assertEqual(summary["parameters"]["years"], 1)
        self.assertEqual(params["years"], 1)

    def test_run_chunk_persists_capacity_status_for_bad_json_stdout(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        proc = types.SimpleNamespace(
            stdout="not json",
            stderr="QuantConnect Cloud has no spare nodes available",
            returncode=1,
        )

        with mock.patch.object(mod.subprocess, "run", return_value=proc):
            out = mod.run_chunk(tmp, 0, 5)

        self.assertEqual(out["status"], "BLOCKED_QC_CLOUD_NO_SPARE_NODES")
        reloaded = json.loads((tmp / "chunk-0.stdout.json").read_text())
        self.assertEqual(reloaded["status"], "BLOCKED_QC_CLOUD_NO_SPARE_NODES")

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

    def test_aggregate_keeps_qc_capacity_out_of_historical_failed_chunks(self):
        mod = load_script("earnings-qc-research")
        out = mod.aggregate([{
            "ok": True,
            "calendar_row_count": 1,
            "qc_processed_row_count": 1,
            "candidate_details": [{"symbol": "A", "earnings_date": "2026-08-01"}],
            "funnel": {},
            "chunk_multiyear_backtest": {"ok": False, "status": "BLOCKED_QC_CLOUD_NO_SPARE_NODES", "results": []},
        }])
        self.assertEqual(out["status"], "BLOCKED_QC_CLOUD_NO_SPARE_NODES")
        self.assertEqual(out["historical_failed_chunk_count"], 0)
        self.assertTrue(out["qc_capacity_blocked"])
        self.assertEqual(out["qc_capacity_status"], "BLOCKED_QC_CLOUD_NO_SPARE_NODES")
        self.assertFalse(out["multiyear_failed"])

    def test_aggregate_capacity_blocker_prevents_ok_even_with_other_final_candidate(self):
        mod = load_script("earnings-qc-research")
        passing_result = {
            "symbol": "A",
            "status": "OK",
            "sample_size": 12,
            "win_rate": 0.6,
            "mean_return_pct": 5.0,
            "median_return_pct": 1.0,
            "leave_one_out_mean_return_pct": 1.0,
            "dropout_pct": 0.0,
            "max_drawdown_pct": 10,
            "max_loss_pct": -20,
            "window_results": PASSING_WINDOWS,
        }
        out = mod.aggregate([
            {
                "ok": True,
                "calendar_row_count": 2,
                "qc_processed_row_count": 1,
                "candidate_details": [{"symbol": "A", "earnings_date": "2026-08-01"}],
                "funnel": {},
                "chunk_multiyear_backtest": {"ok": True, "status": "OK_MULTIYEAR_OPTION_PNL_BACKTEST", "results": [passing_result]},
            },
            {
                "ok": True,
                "calendar_row_count": 2,
                "qc_processed_row_count": 1,
                "candidate_details": [{"symbol": "B", "earnings_date": "2026-08-02"}],
                "funnel": {},
                "chunk_multiyear_backtest": {"ok": False, "status": "BLOCKED_QC_CLOUD_NO_SPARE_NODES", "results": []},
            },
        ])
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "BLOCKED_QC_CLOUD_NO_SPARE_NODES")
        self.assertTrue(out["qc_capacity_blocked"])
        self.assertEqual(out["final_candidate_count"], 1)
        self.assertEqual(out["historical_failed_chunk_count"], 0)

    def test_refresh_summary_preserves_capacity_status(self):
        mod = load_script("earnings-qc-research")
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "full_summary.json").write_text(json.dumps({
            "calendar_row_count": 1,
            "calendar_universe_count": 1,
            "qc_symbols_scanned": 1,
            "chunk_count": 1,
            "aggregate_funnel": {},
            "forward_candidates": [{"symbol": "WMT"}],
            "final_candidates": [],
        }))
        mb = {"ok": False, "status": "BLOCKED_QC_CLOUD_NO_SPARE_NODES", "results": []}
        out = mod.refresh_summary_after_historical(tmp, mb)
        self.assertEqual(out["status"], "BLOCKED_QC_CLOUD_NO_SPARE_NODES")
        self.assertTrue(out["qc_capacity_blocked"])
        self.assertFalse(out["multiyear_failed"])
        self.assertNotEqual(out["status"], "BLOCKED_MULTIYEAR_OPTION_PNL_BACKTEST")

if __name__ == "__main__":
    unittest.main()
