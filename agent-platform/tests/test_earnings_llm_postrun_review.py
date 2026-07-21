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
        self.assertIn("flock -n 9", text)
        self.assertIn("finished_at IS NOT NULL", text)
        self.assertIn("campaign_id = 'daily-earnings-otm'", text)
        self.assertIn("USING_LEGACY_DAILY_RUN_FALLBACK", text)
        self.assertIn("parameters_json->>'to_stage'", text)
        self.assertIn("parameters_json->>'calendar_source'", text)
        self.assertIn("trading-research-runner-codex", text)
        self.assertIn("trading-research-bounded-earnings-qc", text)
        self.assertIn("execute exactly one bounded follow-up action", text)
        self.assertIn("The wrapper is the execution guardrail", text)
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
        self.assertIn("execute exactly one bounded follow-up action", text)
        self.assertNotIn("REVIEW/RECOMMENDATION ONLY", text)
        self.assertNotIn("Do not execute follow-up", text)


if __name__ == "__main__":
    unittest.main()
