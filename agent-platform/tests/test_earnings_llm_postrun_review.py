import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "agent-platform/scripts/earnings-qc-options/earnings-llm-postrun-review"


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
        self.assertIn("POSTRUN_ALREADY_REVIEWED", text)
        self.assertIn("completed-runs", text)
        self.assertIn("flock -n 9", text)
        self.assertIn("finished_at IS NOT NULL", text)
        self.assertIn("campaign_id = 'daily-earnings-otm'", text)
        self.assertIn("USING_LEGACY_DAILY_RUN_FALLBACK", text)
        self.assertIn("parameters_json->>'to_stage'", text)
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


    def test_empty_request_file_is_invalid_not_no_request(self):
        text = SCRIPT.read_text()
        self.assertIn('if [[ "$RC" -eq 0 && -e "$REQUEST_FILE" ]]; then', text)
        self.assertNotIn('if [[ "$RC" -eq 0 && -s "$REQUEST_FILE" ]]; then', text)
        self.assertLess(text.index('-e "$REQUEST_FILE"'), text.index('invalid bounded_action_request.json'))


    def test_research_blocker_returncode_two_counts_as_executed_action(self):
        text = SCRIPT.read_text()
        self.assertIn('EXECUTED_RESEARCH_BLOCKED', text)
        self.assertIn('elif [[ "$BOUNDED_ACTION_RC" -eq 2 ]] && python3', text)
        self.assertIn("status.startswith(('BLOCKED_', 'PARTIAL_')) or terminal_no_trade", text)
        self.assertIn("NO_FORWARD_CANDIDATES", text)
        self.assertIn("NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL", text)
        self.assertIn('earnings-qc-research returns rc=2 for completed research no-trade/blocker', text)
        self.assertIn('"$BOUNDED_ACTION_STATUS" == "EXECUTED_RESEARCH_BLOCKED"', text)


if __name__ == "__main__":
    unittest.main()
