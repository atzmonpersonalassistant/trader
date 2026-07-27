import subprocess
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
