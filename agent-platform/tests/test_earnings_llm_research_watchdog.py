import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "agent-platform/scripts/earnings-qc-options/earnings-llm-research-watchdog"


class EarningsLlmResearchWatchdogTests(unittest.TestCase):
    def test_script_syntax_is_valid(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_rejects_bad_date_before_runtime_state(self):
        result = subprocess.run(
            [str(SCRIPT), "--date", "2026-aa-24", "--dry-run"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 64)
        self.assertIn("YYYY-MM-DD", result.stderr)

    def test_watchdog_is_llm_only_and_never_requests_actions(self):
        text = SCRIPT.read_text()
        self.assertIn("LLM-only watchdog", text)
        self.assertIn("It never runs QC/LEAN", text)
        self.assertIn("do not run QC/LEAN", text)
        self.assertIn("do not run /agents/research/bin/earnings-qc-research", text)
        self.assertIn("do not request or execute bounded actions", text)
        self.assertIn("diagnosis.json", text)
        self.assertIn("notify.txt", text)
        self.assertIn("WATCHDOG_NO_CHANGE", text)
        self.assertIn("WATCHDOG_COMPLETED", text)
        self.assertIn("last-fingerprint.txt", text)
        self.assertIn("trading-research-watchdog-codex", text)
        self.assertNotIn("bounded_action_request.json", text)
        self.assertNotIn("trading-research-bounded-earnings-qc", text)
        self.assertNotIn("earnings-qc-research run", text)
        self.assertNotIn("retry-failed", text)

    def test_fingerprint_gates_repeated_llm_spend(self):
        text = SCRIPT.read_text()
        self.assertIn("FINGERPRINT=", text)
        self.assertIn("LAST_FINGERPRINT_FILE", text)
        self.assertIn('"$(cat "$LAST_FINGERPRINT_FILE")" == "$FINGERPRINT"', text)
        self.assertLess(text.index("WATCHDOG_NO_CHANGE"), text.index("trading-research-watchdog-codex"))

    def test_fingerprint_ignores_churning_log_files(self):
        text = SCRIPT.read_text()
        fingerprint_block = text[text.index('FINGERPRINT="$(python3'):text.index('LAST_FINGERPRINT_FILE=')]
        self.assertIn('full_summary.json', fingerprint_block)
        self.assertIn('run_metadata.json', fingerprint_block)
        self.assertNotIn('DAILY_LOG', fingerprint_block)
        self.assertNotIn('POSTRUN_LOG', fingerprint_block)
        self.assertNotIn('daily_log', fingerprint_block)
        self.assertNotIn('postrun_log', fingerprint_block)

    def test_watchdog_runner_inputs_use_watchdog_user_acl(self):
        text = SCRIPT.read_text()
        helper = text[text.index('make_runner_inputs_usable()'):text.index('while [[ $# -gt 0 ]]')]
        self.assertIn('agent-research-watchdog', helper)
        self.assertIn('\"$HANDOFF_DIR\"', helper)
        self.assertNotIn('agent-research-runner', helper)
        self.assertIn('sudo -n -u agent-research-watchdog', text)
        self.assertIn('trading-research-watchdog-codex', text)

    def test_success_requires_durable_diagnosis_artifacts_before_fingerprint(self):
        text = SCRIPT.read_text()
        self.assertIn('HAS_DIAGNOSIS_MD=0', text)
        self.assertIn('ARTIFACTS_VALID=0', text)
        self.assertIn('"artifacts_valid": $ARTIFACTS_VALID', text)
        self.assertIn('if [[ "$RC" -eq 0 && "$ARTIFACTS_VALID" -eq 1 ]]; then', text)
        self.assertLess(text.index('ARTIFACTS_VALID=0'), text.index("printf '%s\\n' \"$FINGERPRINT\" > \"$LAST_FINGERPRINT_FILE\""))
        self.assertIn('WATCHDOG_FAILED run_id=$RUN_ID rc=$RC artifacts_valid=$ARTIFACTS_VALID', text)

    def run_watchdog_with_fake_psql(self, psql_outputs, now="2026-08-04T10:00:00+03:00", cron_line=None, *, root=None, date="2026-08-04", schedule=None, schedule_zone=None):
        cleanup = TemporaryDirectory() if root is None else None
        try:
            root = Path(cleanup.name) if cleanup is not None else Path(root)
            fake_bin = root / "bin"
            fake_bin.mkdir(exist_ok=True)
            state_dir = root / "state"
            handoff_dir = root / "handoff"
            report_root = root / "reports"
            log_dir = root / "logs"
            skill = root / "SKILL.md"
            calls = root / "psql-calls"
            crontab_calls = root / "crontab-calls"
            crontab_output = root / "crontab-output"
            calls.unlink(missing_ok=True)
            skill.write_text("# skill\n")
            happy_run_dir = report_root / "run"
            happy_run_dir.mkdir(parents=True, exist_ok=True)
            (happy_run_dir / "full_summary.json").write_text('{"status":"NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL"}')
            resolved_outputs = [
                output.replace("{report_root}", str(report_root))
                for output in psql_outputs
            ]
            script = fake_bin / "psql"
            script.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                f"calls={calls!s}\n"
                "n=0\n"
                "[[ -f \"$calls\" ]] && n=$(cat \"$calls\")\n"
                "n=$((n + 1))\n"
                "printf '%s' \"$n\" > \"$calls\"\n"
                "case \"$n\" in\n"
                + "".join(
                    f"  {idx}) printf '%b' {output!r} ;;\n"
                    for idx, output in enumerate(resolved_outputs, start=1)
                )
                + "  *) printf '' ;;\n"
                "esac\n"
            )
            script.chmod(0o755)
            (fake_bin / "flock").write_text("#!/usr/bin/env bash\nexit 0\n")
            (fake_bin / "flock").chmod(0o755)
            if cron_line is not None:
                (fake_bin / "crontab").write_text(
                    "#!/usr/bin/env bash\n"
                    f"printf x >> {crontab_calls!s}\n"
                    "if [[ \"${1:-}\" == \"-l\" ]]; then\n"
                    f"  printf '%s\\n' {cron_line!r} | tee -a {crontab_output!s}\n"
                    "  exit 0\n"
                    "fi\n"
                    "exit 64\n"
                )
                (fake_bin / "crontab").chmod(0o755)
            result = subprocess.run(
                [str(SCRIPT), "--date", date, "--dry-run"],
                env={
                    **os.environ,
                    "PATH": f"{fake_bin}:/usr/bin:/bin",
                    "EARNINGS_WATCHDOG_PATH_PREFIX": str(fake_bin),
                    "EARNINGS_WATCHDOG_STATE_DIR": str(state_dir),
                    "EARNINGS_WATCHDOG_HANDOFF_DIR": str(handoff_dir),
                    "EARNINGS_WATCHDOG_REPORT_ROOT": str(report_root),
                    "EARNINGS_WATCHDOG_LOG_DIR": str(log_dir),
                    "EARNINGS_WATCHDOG_SKILL_FILE": str(skill),
                    "EARNINGS_WATCHDOG_STALE_RUNNING_SECONDS": "3600",
                    "EARNINGS_WATCHDOG_MISSING_RUN_GRACE_SECONDS": "3600",
                    "EARNINGS_WATCHDOG_NOW": now,
                    **({"EARNINGS_WATCHDOG_DAILY_SCHEDULE": schedule} if schedule is not None else {}),
                    **({"EARNINGS_WATCHDOG_DAILY_SCHEDULE_ZONE": schedule_zone} if schedule_zone is not None else {}),
                },
                text=True,
                capture_output=True,
                check=False,
            )
            result.crontab_call_count = crontab_calls.read_text().count("x") if crontab_calls.exists() else 0
            result.crontab_output = crontab_output.read_text() if crontab_output.exists() else ""
            result.handoff_tasks = {
                path.name: path.read_text()
                for path in handoff_dir.glob("*-task.txt")
            }
            return result
        finally:
            if cleanup is not None:
                cleanup.cleanup()

    def test_stale_running_daily_run_escalates(self):
        result = self.run_watchdog_with_fake_psql([
            "",
            "earnings-qc-options-scan-full-20260804-060000|running|2026-08-04 06:00:00+03||7201|{report_root}/run\n",
        ])

        self.assertEqual(result.returncode, 75)
        self.assertIn("STALE_RUNNING_DAILY_RUN", result.stderr)
        self.assertIn("threshold_seconds=3600", result.stderr)
        self.assertEqual(len(result.handoff_tasks), 1)
        task_text = next(iter(result.handoff_tasks.values()))
        self.assertIn("condition: STALE_RUNNING_DAILY_RUN", task_text)
        self.assertIn("date: 2026-08-04", task_text)
        self.assertIn("threshold_seconds: 3600", task_text)

    def test_date_with_no_daily_run_row_escalates(self):
        result = self.run_watchdog_with_fake_psql(["", ""])

        self.assertEqual(result.returncode, 75)
        self.assertIn("DAILY_RUN_MISSING_AFTER_DEADLINE date=2026-08-04", result.stderr)
        self.assertIn("scheduled_at=06:00", result.stderr)
        self.assertIn("grace_seconds=3600", result.stderr)
        self.assertEqual(len(result.handoff_tasks), 1)
        task_text = next(iter(result.handoff_tasks.values()))
        self.assertIn("condition: DAILY_RUN_MISSING_AFTER_DEADLINE", task_text)
        self.assertIn("date: 2026-08-04", task_text)
        self.assertIn("scheduled_at: 06:00", task_text)
        self.assertIn("grace_seconds: 3600", task_text)

    def test_date_with_no_daily_run_row_before_daily_is_due_is_not_due_yet(self):
        result = self.run_watchdog_with_fake_psql(["", ""], now="2026-08-04T05:30:00+03:00")

        self.assertEqual(result.returncode, 0)
        self.assertIn("DAILY_RUN_NOT_DUE_YET date=2026-08-04", result.stdout)
        self.assertNotIn("DAILY_RUN_MISSING_AFTER_DEADLINE", result.stderr)

    def test_date_with_no_daily_run_row_after_due_within_grace_is_pending(self):
        result = self.run_watchdog_with_fake_psql(["", ""], now="2026-08-04T06:30:00+03:00")

        self.assertEqual(result.returncode, 0)
        self.assertIn("DAILY_RUN_MISSING_WITHIN_GRACE date=2026-08-04", result.stdout)

    def test_missing_daily_row_uses_cron_schedule_override(self):
        result = self.run_watchdog_with_fake_psql(
            ["", ""],
            now="2026-08-04T06:30:00+03:00",
            cron_line="45 6 * * * /agents/research/bin/earnings-otm-daily.sh",
        )

        self.assertEqual(result.returncode, 0)
        self.assertGreater(result.crontab_call_count, 0)
        self.assertIn("/agents/research/bin/earnings-otm-daily.sh", result.crontab_output)
        self.assertIn("DAILY_RUN_NOT_DUE_YET date=2026-08-04", result.stdout)
        self.assertIn("scheduled_at=06:45", result.stdout)

    def test_missing_daily_row_uses_explicit_schedule_zone(self):
        result = self.run_watchdog_with_fake_psql(
            ["", ""],
            now="2026-08-04T06:30:00+03:00",
            schedule="06:00",
            schedule_zone="UTC",
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("DAILY_RUN_NOT_DUE_YET date=2026-08-04", result.stdout)
        self.assertIn("scheduled_at=06:00", result.stdout)

    def test_missing_daily_row_default_schedule_matches_managed_timer_zone(self):
        result = self.run_watchdog_with_fake_psql(
            ["", ""],
            now="2026-08-04T06:30:00+03:00",
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("DAILY_RUN_MISSING_WITHIN_GRACE date=2026-08-04", result.stdout)
        text = SCRIPT.read_text()
        self.assertIn('DAILY_RUN_DEFAULT_ZONE="Asia/Jerusalem"', text)
        self.assertIn('tz = ZoneInfo(zone_s)', text)

    def test_failure_handoffs_are_deduped_by_date_and_condition(self):
        with TemporaryDirectory() as tmp:
            first = self.run_watchdog_with_fake_psql(["", ""], root=tmp)
            second = self.run_watchdog_with_fake_psql(["", ""], root=tmp)
            next_day = self.run_watchdog_with_fake_psql(
                ["", ""],
                root=tmp,
                date="2026-08-05",
                now="2026-08-05T10:00:00+03:00",
            )

            self.assertEqual(first.returncode, 75)
            self.assertEqual(second.returncode, 75)
            self.assertIn("HANDOFF_TASK_WRITTEN condition=DAILY_RUN_MISSING_AFTER_DEADLINE", first.stdout)
            self.assertIn("HANDOFF_TASK_ALREADY_WRITTEN condition=DAILY_RUN_MISSING_AFTER_DEADLINE", second.stdout)
            self.assertEqual(
                len([name for name in second.handoff_tasks if "DAILY_RUN_MISSING_AFTER_DEADLINE" in name]),
                1,
            )
            self.assertEqual(
                len([name for name in next_day.handoff_tasks if "DAILY_RUN_MISSING_AFTER_DEADLINE" in name]),
                2,
            )

    def test_finished_happy_path_still_reaches_dry_run_without_llm(self):
        result = self.run_watchdog_with_fake_psql([
            "",
            "earnings-qc-options-scan-full-20260804-060000|completed|2026-08-04 06:00:00+03|2026-08-04 07:00:00+03|0|{report_root}/run\n",
            "earnings-qc-options-scan-full-20260804-060000\tcompleted\tNO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL\t2026-08-04 07:00:00+03\t{report_root}/run\t0\t\t\n",
        ])

        self.assertEqual(result.returncode, 0)
        self.assertIn("WOULD_RUN_WATCHDOG run_id=earnings-qc-options-scan-full-20260804-060000", result.stdout)


if __name__ == "__main__":
    unittest.main()
