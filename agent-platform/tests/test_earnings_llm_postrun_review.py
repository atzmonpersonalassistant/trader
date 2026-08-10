import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "agent-platform/scripts/earnings-qc-options/earnings-llm-postrun-review"
CLASSIFIER = ROOT / "agent-platform/scripts/earnings-qc-options/earnings-qc-classify-bounded-action"
PRECHECK = ROOT / "agent-platform/scripts/earnings-qc-options/earnings-qc-precheck-bounded-action"


class EarningsLlmPostrunReviewTests(unittest.TestCase):
    def test_script_syntax_is_valid(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_rejects_non_digit_date_before_touching_runtime_state(self):
        result = subprocess.run(
            [str(SCRIPT), "--date", "2026-aa-21", "--dry-run"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 64)
        self.assertIn("YYYY-MM-DD", result.stderr)

    def test_required_noop_and_runner_guards_are_encoded(self):
        text = SCRIPT.read_text()
        self.assertIn("POSTRUN_REVIEW_ALREADY_RUNNING", text)
        self.assertIn("NO_FINISHED_DAILY_RUN", text)
        self.assertIn("HANDOFF_TASK_WRITTEN condition=$condition", text)
        self.assertIn("POSTRUN_ALREADY_REVIEWED", text)
        self.assertIn("completed-runs", text)

    def run_postrun_with_fake_psql(self, psql_outputs, *, root=None, date="2026-08-04", now=None, extra_env=None):
        cleanup = tempfile.TemporaryDirectory() if root is None else None
        try:
            root = Path(cleanup.name) if cleanup is not None else Path(root)
            fake_bin = root / "bin"
            fake_bin.mkdir(exist_ok=True)
            state_dir = root / "state"
            handoff_dir = root / "handoff"
            report_root = root / "reports"
            skill = root / "SKILL.md"
            calls = root / "psql-calls"
            calls.unlink(missing_ok=True)
            skill.write_text("# skill\n")
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
                    for idx, output in enumerate(psql_outputs, start=1)
                )
                + "  *) printf '' ;;\n"
                "esac\n"
            )
            script.chmod(0o755)
            (fake_bin / "flock").write_text("#!/usr/bin/env bash\nexit 0\n")
            (fake_bin / "flock").chmod(0o755)
            env = {
                **os.environ,
                "PATH": f"{fake_bin}:/usr/bin:/bin",
                "EARNINGS_POSTRUN_PATH_PREFIX": str(fake_bin),
                "EARNINGS_POSTRUN_STATE_DIR": str(state_dir),
                "EARNINGS_POSTRUN_HANDOFF_DIR": str(handoff_dir),
                "EARNINGS_POSTRUN_REPORT_ROOT": str(report_root),
                "EARNINGS_POSTRUN_SKILL_FILE": str(skill),
                **({"EARNINGS_POSTRUN_NOW": now} if now is not None else {}),
                **(extra_env or {}),
            }
            result = subprocess.run(
                [str(SCRIPT), "--date", date, "--dry-run"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            result.handoff_tasks = {
                path.name: path.read_text()
                for path in handoff_dir.glob("*-task.txt")
            }
            result.failure_handoff_markers = sorted(
                path.name for path in (state_dir / "failure-handoffs").glob("*")
            )
            return result
        finally:
            if cleanup is not None:
                cleanup.cleanup()

    def test_no_finished_daily_run_writes_handoff_task(self):
        result = self.run_postrun_with_fake_psql(
            ["", "", ""],
            extra_env={
                "EARNINGS_POSTRUN_MISSING_RUN_GRACE_SECONDS": "3600",
                "EARNINGS_POSTRUN_STALE_RUNNING_SECONDS": "3600",
            },
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("NO_FINISHED_DAILY_RUN date=2026-08-04", result.stdout)
        self.assertEqual(len(result.handoff_tasks), 1)
        task_text = next(iter(result.handoff_tasks.values()))
        self.assertIn("condition: NO_FINISHED_DAILY_RUN", task_text)
        self.assertIn("date: 2026-08-04", task_text)
        self.assertIn("scheduled_at: 10:30", task_text)
        self.assertIn("grace_seconds: 3600", task_text)

    def test_default_missing_run_deadline_is_1330_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_postrun_with_fake_psql(
                ["", "", ""],
                root=tmp,
                now="2026-08-04T13:29:59+03:00",
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("DAILY_RUN_NOT_DUE_YET date=2026-08-04", result.stdout)
            self.assertIn("scheduled_at=10:30", result.stdout)
            self.assertIn("grace_seconds=10800", result.stdout)
            self.assertIn("due_at=2026-08-04T13:30:00+03:00", result.stdout)
            self.assertNotIn("NO_FINISHED_DAILY_RUN", result.stdout)
            self.assertEqual(result.handoff_tasks, {})
            self.assertEqual(result.failure_handoff_markers, [])

    def test_no_finished_daily_run_before_deadline_does_not_write_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_postrun_with_fake_psql(
                ["", "", ""],
                root=tmp,
                now="2026-08-04T08:29:59Z",
                extra_env={"EARNINGS_POSTRUN_MISSING_RUN_GRACE_SECONDS": "3600"},
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("DAILY_RUN_NOT_DUE_YET date=2026-08-04", result.stdout)
            self.assertIn("due_at=2026-08-04T11:30:00+03:00", result.stdout)
            self.assertNotIn("HANDOFF_TASK_", result.stdout)
            self.assertEqual(result.handoff_tasks, {})
            self.assertEqual(result.failure_handoff_markers, [])

    def test_no_finished_daily_run_after_deadline_writes_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_postrun_with_fake_psql(
                ["", "", ""],
                root=tmp,
                now="2026-08-04T11:30:00+03:00",
                extra_env={"EARNINGS_POSTRUN_MISSING_RUN_GRACE_SECONDS": "3600"},
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("HANDOFF_TASK_WRITTEN condition=NO_FINISHED_DAILY_RUN", result.stdout)
            self.assertIn("NO_FINISHED_DAILY_RUN date=2026-08-04", result.stdout)
            self.assertIn("due_at=2026-08-04T11:30:00+03:00", result.stdout)
            self.assertEqual(len(result.handoff_tasks), 1)
            self.assertEqual(result.failure_handoff_markers, ["20260804-NO_FINISHED_DAILY_RUN"])

    def test_finished_daily_run_before_missing_deadline_uses_normal_review_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            (run_dir / "full_summary.json").write_text("{}\n")
            row = (
                "earnings-qc-options-scan-full-20260804-073000-attempt-1\t"
                "completed\tNO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL\t"
                f"2026-08-04 07:35:00+00\t{run_dir}\t0\tliquidity\t\n"
            )
            result = self.run_postrun_with_fake_psql(
                ["", "", row],
                root=tmp,
                now="2026-08-04T09:29:59Z",
                extra_env={"EARNINGS_POSTRUN_MISSING_RUN_GRACE_SECONDS": "3600"},
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("WOULD_RUN run_id=earnings-qc-options-scan-full-20260804-073000-attempt-1", result.stdout)
            self.assertNotIn("DAILY_RUN_NOT_DUE_YET", result.stdout)
            self.assertNotIn("NO_FINISHED_DAILY_RUN", result.stdout)
            self.assertEqual(result.handoff_tasks, {})
            self.assertEqual(result.failure_handoff_markers, [])

    def test_retry_waiting_daily_run_blocks_transient_failed_attempt_review(self):
        result = self.run_postrun_with_fake_psql([
            "",
            "earnings-qc-options-scan-full-20260804-retry-waiting-attempt-2\t2026-08-04T10:35:00Z\n",
            "earnings-qc-options-scan-full-20260804-083500-attempt-1\tblocked\tBLOCKED_QC_CLOUD_NO_SPARE_NODES\t2026-08-04 08:40:00+00\t{report_root}/run\t0\tBLOCKED_QC_CLOUD_NO_SPARE_NODES\t\n",
        ], now="2026-08-04T09:30:00Z")

        self.assertEqual(result.returncode, 0)
        self.assertIn("POSTRUN_DAILY_RETRY_WAITING", result.stdout)
        self.assertIn("next_attempt_at_utc=2026-08-04T10:35:00Z", result.stdout)
        self.assertEqual(len(result.handoff_tasks), 0)

    def test_no_finished_daily_run_handoff_is_deduped_by_date_and_condition(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.run_postrun_with_fake_psql(["", "", ""], root=tmp, now="2026-08-04T13:30:00+03:00")
            second = self.run_postrun_with_fake_psql(["", "", ""], root=tmp, now="2026-08-04T13:30:00+03:00")
            third = self.run_postrun_with_fake_psql(["", "", ""], root=tmp, now="2026-08-04T13:30:00+03:00")
            next_day = self.run_postrun_with_fake_psql(["", "", ""], root=tmp, date="2026-08-05")

            self.assertEqual(first.returncode, 0)
            self.assertEqual(second.returncode, 0)
            self.assertEqual(third.returncode, 0)
            self.assertIn("HANDOFF_TASK_WRITTEN condition=NO_FINISHED_DAILY_RUN", first.stdout)
            self.assertIn("HANDOFF_TASK_ALREADY_WRITTEN condition=NO_FINISHED_DAILY_RUN", second.stdout)
            self.assertIn("HANDOFF_TASK_ALREADY_WRITTEN condition=NO_FINISHED_DAILY_RUN", third.stdout)
            self.assertEqual(
                len([name for name in third.handoff_tasks if "NO_FINISHED_DAILY_RUN" in name]),
                1,
            )
            self.assertEqual(
                len([name for name in next_day.handoff_tasks if "NO_FINISHED_DAILY_RUN" in name]),
                2,
            )

    def test_daily_selector_requires_explicit_daily_stage_parameters(self):
        text = SCRIPT.read_text()
        self.assertIn("parameters_json->>'from_stage' = 'calendar'", text)
        self.assertIn("parameters_json->>'to_stage' = 'historical_option_pnl'", text)
        self.assertNotIn("COALESCE(parameters_json->>'from_stage','calendar') = 'calendar'", text)
        self.assertNotIn("COALESCE(parameters_json->>'to_stage','historical_option_pnl') = 'historical_option_pnl'", text)
        self.assertIn("flock -n 9", text)
        self.assertIn("finished_at IS NOT NULL", text)
        self.assertIn("campaign_id = 'daily-earnings-otm'", text)
        self.assertIn("USING_LEGACY_DAILY_RUN_FALLBACK", text)
        self.assertIn("parameters_json->>'to_stage'", text)
        self.assertIn("parameters_json->>'no_outbox' = 'false'", text)
        self.assertEqual(text.count("parameters_json->>'no_outbox' = 'false'"), 2)
        self.assertNotIn("COALESCE((parameters_json->>'no_outbox')::boolean, false) = false", text)
        self.assertIn("parameters_json->>'calendar_source'", text)
        self.assertIn("trading-research-runner-codex", text)
        self.assertIn("trading-research-bounded-earnings-qc", text)
        self.assertIn("request exactly one bounded follow-up action", text)
        self.assertIn("The wrapper remains the execution guardrail", text)
        self.assertIn("bounded_action_request.json", text)
        self.assertIn("--bounded-action-dir __ACTION_DIR__", text)
        self.assertIn("The action id is one-use", text)
        self.assertIn("Do not send any message yourself", text)

    def test_task_heredoc_is_single_quoted_to_prevent_prompt_command_substitution(self):
        text = SCRIPT.read_text()
        self.assertIn("cat > \"$TASK_FILE\" <<'TASK'", text)
        self.assertIn("__BOUNDED_ACTION_ID__", text)
        self.assertIn("__SKILL_CONTENT__", text)
        self.assertIn("pathlib.Path(task_file).write_text(text)", text)

    def test_runner_permissions_are_prepared_for_approved_isolated_runner(self):
        text = SCRIPT.read_text()
        self.assertIn("make_runner_inputs_usable", text)
        self.assertIn("agent-research-runner:rwx", text)
        self.assertIn("trading-research-runner-codex", text)
        self.assertIn("trading-research-bounded-earnings-qc", text)
        self.assertIn("request exactly one bounded follow-up action", text)
        self.assertNotIn("REVIEW/RECOMMENDATION ONLY", text)
        self.assertNotIn("Do not execute follow-up", text)

    def test_bounded_request_parser_validates_before_loading_args(self):
        text = SCRIPT.read_text()
        self.assertIn("BOUNDED_ACTION_ARGV_NUL", text)
        self.assertIn("set(data.keys()) != {'argv'}", text)
        self.assertIn("HOST_ACTION_DIR", text)
        self.assertIn("os.O_EXCL", text)
        self.assertIn("os.replace(tmp, out_path)", text)
        self.assertIn("if ! python3 - \"$REQUEST_FILE\" \"$BOUNDED_ACTION_ARGV_NUL\"", text)
        self.assertIn('BOUNDED_ACTION_STATUS="INVALID_REQUEST"', text)
        self.assertLess(text.index("os.replace(tmp, out_path)"), text.index("mapfile -d '' BOUNDED_ACTION_ARGS"))
        self.assertLess(text.index("mapfile -d '' BOUNDED_ACTION_ARGS"), text.index("cd \"$OUTPUT_DIR\" && /usr/local/sbin/trading-research-bounded-earnings-qc"))


    def test_host_action_artifacts_do_not_write_directly_into_runner_controlled_paths(self):
        text = SCRIPT.read_text()
        self.assertIn('HOST_ACTION_DIR="$STATE_DIR/host-action/$BOUNDED_ACTION_ID"', text)
        self.assertIn('BOUNDED_STDOUT="$HOST_ACTION_DIR/bounded-action.stdout.log"', text)
        self.assertIn('BOUNDED_STDERR="$HOST_ACTION_DIR/bounded-action.stderr.log"', text)
        self.assertIn('"$HOST_ACTION_DIR/bounded_action_result.json"', text)
        self.assertIn('runner-controlled artifact path already exists', text)
        self.assertIn('BOUNDED_ACTION_COPY_BACK_CONFLICT', text)
        self.assertIn('bounded_action_copy_back_returncode', text)
        self.assertIn('bounded_action_copy_conflicts.txt', text)
        self.assertIn('os.O_CREAT | os.O_EXCL', text)


    def test_completed_run_marker_prevents_repeated_five_minute_actions(self):
        text = SCRIPT.read_text()
        self.assertIn('COMPLETED_MARKER_DIR="$STATE_DIR/completed-runs/$SAFE_RUN_MARKER"', text)
        self.assertIn('POSTRUN_ALREADY_REVIEWED', text)
        self.assertLess(text.index('POSTRUN_ALREADY_REVIEWED'), text.index('TASK_FILE="$HANDOFF_DIR/research-pass-postrun-'))
        self.assertIn('mkdir "$COMPLETED_MARKER_DIR"', text)
        self.assertIn('bounded_action_status.txt', text)

    def test_failure_handoff_marker_prevents_repeated_no_run_artifacts(self):
        text = SCRIPT.read_text()
        self.assertIn('marker_dir="$STATE_DIR/failure-handoffs/${DATE_COMPACT}-${condition}"', text)
        self.assertIn('HANDOFF_TASK_ALREADY_WRITTEN condition=$condition', text)
        self.assertIn('tmp_task_file="$(mktemp "$HANDOFF_DIR/.research-pass-postrun-', text)
        self.assertLess(text.index('cat > "$tmp_task_file"'), text.index('if ! mkdir "$marker_dir"'))
        self.assertLess(text.index('if ! mkdir "$marker_dir"'), text.index('if ! mv "$tmp_task_file" "$task_file"'))
        self.assertIn('rmdir "$marker_dir"', text)


    def test_copy_back_conflicts_are_nonfatal_after_action_execution(self):
        text = SCRIPT.read_text()
        self.assertIn("python3 - \"$HOST_ACTION_DIR\" \"$OUTPUT_DIR\" <<'PY' || COPY_BACK_RC=$?", text)
        self.assertIn('if [[ "$COPY_BACK_RC" -ne 0 ]]', text)
        self.assertLess(text.index('BOUNDED_ACTION_COPY_BACK_CONFLICT'), text.index('cat > "$OUTPUT_DIR/run_metadata.json"'))
        self.assertLess(text.index('cat > "$OUTPUT_DIR/run_metadata.json"'), text.index('mkdir "$COMPLETED_MARKER_DIR"'))


    def test_symlink_request_invalid_path_does_not_mapfile_missing_argv(self):
        text = SCRIPT.read_text()
        self.assertLess(text.index('[[ ! -L "$REQUEST_FILE" ]]'), text.index('if [[ "$BOUNDED_ACTION_STATUS" != "INVALID_REQUEST" ]]; then'))
        self.assertLess(text.index('if [[ "$BOUNDED_ACTION_STATUS" != "INVALID_REQUEST" ]]; then'), text.index('if ! python3 - "$REQUEST_FILE" "$BOUNDED_ACTION_ARGV_NUL"'))
        self.assertLess(text.index('if ! python3 - "$REQUEST_FILE" "$BOUNDED_ACTION_ARGV_NUL"'), text.index("mapfile -d '' BOUNDED_ACTION_ARGS"))


    def test_failed_bounded_action_does_not_mark_run_completed(self):
        text = SCRIPT.read_text()
        self.assertIn('"$BOUNDED_ACTION_STATUS" == "NO_REQUEST" || "$BOUNDED_ACTION_STATUS" == "EXECUTED"', text)
        self.assertIn('bounded_action_status=$BOUNDED_ACTION_STATUS', text)
        self.assertLess(text.index('bounded_action_status=$BOUNDED_ACTION_STATUS'), text.index('echo "REVIEW_FAILED run_id=$RUN_ID rc=$RC'))

    def test_retry_failed_precondition_refusal_is_recorded_and_completed(self):
        text = SCRIPT.read_text()
        self.assertIn("earnings-qc-precheck-bounded-action", text)
        self.assertIn('REFUSED_RETRY_FAILED_*', text)
        self.assertIn('bounded_action_status.txt', text)
        self.assertLess(
            text.index("earnings-qc-precheck-bounded-action"),
            text.index('cd "$OUTPUT_DIR" && /usr/local/sbin/trading-research-bounded-earnings-qc'),
        )


    def test_empty_request_file_is_invalid_not_no_request(self):
        text = SCRIPT.read_text()
        self.assertIn('if [[ "$RC" -eq 0 && -e "$REQUEST_FILE" ]]; then', text)
        self.assertNotIn('if [[ "$RC" -eq 0 && -s "$REQUEST_FILE" ]]; then', text)
        self.assertLess(text.index('-e "$REQUEST_FILE"'), text.index('invalid bounded_action_request.json'))


    def test_research_blocker_returncode_two_counts_as_executed_action(self):
        text = SCRIPT.read_text() + CLASSIFIER.read_text()
        self.assertIn('EXECUTED_RESEARCH_BLOCKED', text)
        self.assertIn('elif [[ "$BOUNDED_ACTION_RC" -eq 2 ]] && /agents/research/libexec/earnings-qc-options/earnings-qc-classify-bounded-action "$BOUNDED_STDOUT"', text)
        self.assertIn("NO_FORWARD_CANDIDATES", text)
        self.assertIn("NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL", text)
        self.assertIn('earnings-qc-research returns rc=2 for completed research no-trade/blocker', text)
        self.assertIn('"$BOUNDED_ACTION_STATUS" == "EXECUTED_RESEARCH_BLOCKED"', text)

    def test_bounded_action_classifier_accepts_actual_research_stdout_shapes(self):
        payloads = [
            {"ok": False, "status": "NO_FORWARD_CANDIDATES"},
            {"ok": False, "status": "NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL"},
            {
                "ok": False,
                "campaign_id": "daily-earnings-otm",
                "run_id": "run-a",
                "run_dir": "/agents/research/reports/run-a",
                "years": 10,
                "multiyear": {"ok": False, "status": "NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL"},
                "summary": {"ok": False, "status": "NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL"},
            },
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                path = Path(tempfile.mkdtemp()) / "stdout.json"
                path.write_text(json.dumps(payload))
                result = subprocess.run([str(CLASSIFIER), str(path)], check=False)
                self.assertEqual(result.returncode, 0)

    def test_bounded_action_classifier_rejects_wrapper_errors(self):
        path = Path(tempfile.mkdtemp()) / "stdout.json"
        path.write_text(json.dumps({"ok": False, "status": "INVALID_BOUNDED_ACTION"}))
        result = subprocess.run([str(CLASSIFIER), str(path)], check=False)
        self.assertEqual(result.returncode, 1)

    def test_bounded_action_precheck_refuses_retry_failed_with_zero_failed_chunks(self):
        tmp = Path(tempfile.mkdtemp())
        summary = tmp / "full_summary.json"
        result_path = tmp / "bounded_action_result.json"
        summary.write_text(json.dumps({"failed_chunk_count": 0, "failed_chunks": []}))

        result = subprocess.run(
            [str(PRECHECK), str(summary), str(result_path), "retry-failed", "--offset", "650", "--years", "1", "--end-to-end"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("REFUSED_RETRY_FAILED_NO_FAILED_CHUNKS", result.stdout)
        payload = json.loads(result_path.read_text())
        self.assertEqual(payload["status"], "REFUSED_RETRY_FAILED_NO_FAILED_CHUNKS")
        self.assertEqual(payload["returncode"], 65)
        self.assertEqual(payload["argv"][0], "retry-failed")

    def test_bounded_action_precheck_allows_retry_failed_with_failed_chunks(self):
        tmp = Path(tempfile.mkdtemp())
        summary = tmp / "full_summary.json"
        result_path = tmp / "bounded_action_result.json"
        summary.write_text(json.dumps({"failed_chunk_count": 1, "failed_chunks": [{"offset": 650}]}))

        result = subprocess.run(
            [str(PRECHECK), str(summary), str(result_path), "retry-failed", "--offset", "650", "--years", "1", "--end-to-end"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "OK")
        self.assertFalse(result_path.exists())


if __name__ == "__main__":
    unittest.main()
