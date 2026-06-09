import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MVP0AgentTests(unittest.TestCase):
    def test_orchestrator_auto_merge_candidate_requires_agent_label_and_passing_review(self):
        orch = load("trading_orchestrator", "tools/trading_orchestrator.py")
        passing = {"name": "review-agent/pass", "status": "completed", "conclusion": "success"}
        failing = {"name": "review-agent/pass", "status": "completed", "conclusion": "failure"}
        same_repo_pr = {"head": {"ref": "agent/issue-5-docs", "repo": {"full_name": "atzmonpersonalassistant/trader"}}, "base": {"repo": {"full_name": "atzmonpersonalassistant/trader"}}}
        fork_pr = {"head": {"ref": "agent/issue-5-docs", "repo": {"full_name": "evil/fork"}}, "base": {"repo": {"full_name": "atzmonpersonalassistant/trader"}}}
        self.assertTrue(orch.is_trusted_agent_pr(same_repo_pr))
        self.assertFalse(orch.is_trusted_agent_pr(fork_pr))
        self.assertFalse(orch.is_trusted_agent_pr({"head": {"ref": "docs/manual-pr"}}))
        self.assertEqual(orch.is_auto_merge_candidate(["agent:pr-opened"], passing, "agent/issue-5-docs"), (True, "ok"))
        self.assertEqual(orch.is_auto_merge_candidate(["agent:pr-opened"], passing, "docs/manual-pr"), (False, "untrusted_branch"))
        self.assertEqual(orch.is_auto_merge_candidate([], passing, "agent/issue-5-docs"), (False, "missing_agent_pr_opened"))
        self.assertEqual(orch.is_auto_merge_candidate(["agent:pr-opened", "agent:needs-fix"], passing, "agent/issue-5-docs"), (False, "needs_fix"))
        self.assertEqual(orch.is_auto_merge_candidate(["agent:pr-opened", "agent:blocked"], passing, "agent/issue-5-docs"), (False, "blocked"))
        self.assertEqual(orch.is_auto_merge_candidate(["agent:pr-opened"], failing, "agent/issue-5-docs"), (False, "review_not_successful"))
        self.assertEqual(orch.is_auto_merge_candidate(["agent:pr-opened"], None, "agent/issue-5-docs"), (False, "missing_review_check"))

    def test_coding_agent_fix_prompt_includes_review_context(self):
        agent = load("trading_coding_agent", "tools/trading_coding_agent.py")
        prompt = agent.build_prompt(
            {"number": 7, "title": "Fix me", "body": "body"},
            {
                "comments": [{"body": "Review says update the failing edge case."}],
                "check_runs": [{"name": "review-agent/pass", "conclusion": "failure", "output": {"summary": "Missing tests"}}],
            },
        )
        self.assertIn("Fix mode context", prompt)
        self.assertIn("Review says update", prompt)
        self.assertIn("review-agent/pass: failure", prompt)
        self.assertIn("Update the existing PR branch only", prompt)

    def test_coding_agent_fix_pr_requires_trusted_same_repo_agent_branch(self):
        agent = load("trading_coding_agent", "tools/trading_coding_agent.py")
        config = {"repo": "atzmonpersonalassistant/trader", "base_branch": "main"}
        trusted = {
            "number": 12,
            "head": {"ref": "agent/issue-12-docs", "repo": {"full_name": "atzmonpersonalassistant/trader"}},
            "base": {"ref": "main", "repo": {"full_name": "atzmonpersonalassistant/trader"}},
        }
        labels = {"labels": [{"name": "agent:pr-opened"}]}
        self.assertEqual(agent.validate_fix_pr(config, trusted, labels), "agent/issue-12-docs")

        fork = dict(trusted)
        fork["head"] = {"ref": "agent/issue-12-docs", "repo": {"full_name": "evil/trader"}}
        with self.assertRaisesRegex(RuntimeError, "head_repo_mismatch"):
            agent.validate_fix_pr(config, fork, labels)

        manual = dict(trusted)
        manual["head"] = {"ref": "docs/manual", "repo": {"full_name": "atzmonpersonalassistant/trader"}}
        with self.assertRaisesRegex(RuntimeError, "untrusted_branch"):
            agent.validate_fix_pr(config, manual, labels)

        with self.assertRaisesRegex(RuntimeError, "missing_agent_pr_opened_label"):
            agent.validate_fix_pr(config, trusted, {"labels": []})

        with self.assertRaisesRegex(RuntimeError, "blocked_or_rejected"):
            agent.validate_fix_pr(config, trusted, {"labels": [{"name": "agent:pr-opened"}, {"name": "agent:blocked"}]})

    def test_orchestrator_blocked_outbox_is_deduped(self):
        orch = load("trading_orchestrator", "tools/trading_orchestrator.py")
        import sqlite3
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.db"
            orch.init_db(db)
            with sqlite3.connect(db) as conn:
                first = orch.create_blocked_outbox(conn, pr_number=11, title="T", url="https://example/pr/11", reason="retry limit", retry_count=51)
                second = orch.create_blocked_outbox(conn, pr_number=11, title="T", url="https://example/pr/11", reason="retry limit", retry_count=51)
                rows = conn.execute("SELECT external_id, payload_json FROM outbox").fetchall()
        self.assertEqual(first, ("blocked-pr-11", True))
        self.assertEqual(second, ("blocked-pr-11", False))
        self.assertEqual(len(rows), 1)
        self.assertIn("blocked_pr", rows[0][1])

    def test_coding_agent_enforces_docs_only_changes(self):
        agent = load("trading_coding_agent", "tools/trading_coding_agent.py")
        self.assertTrue(agent.is_allowed_mvp0_change("README.md"))
        self.assertTrue(agent.is_allowed_mvp0_change("plans/mvp0-task-breakdown.md"))
        self.assertFalse(agent.is_allowed_mvp0_change("tools/trading_orchestrator.py"))
        self.assertFalse(agent.is_allowed_mvp0_change(".env"))

    def test_review_fetch_pr_context_uses_issue_labels(self):
        review = load("trading_review_agent", "tools/trading_review_agent.py")
        calls = []

        def fake_request(method, url, token, payload=None, accept="application/vnd.github+json"):
            calls.append((method, url, accept))
            if accept == "application/vnd.github.v3.diff":
                return ""
            if url.endswith("/pulls/7"):
                return {"number": 7, "title": "PR", "body": "", "labels": [], "head": {"sha": "abc"}}
            if url.endswith("/issues/7"):
                return {"labels": [{"name": "human:approved"}]}
            if "/files" in url:
                return []
            raise AssertionError(url)

        original = review.github_request
        review.github_request = fake_request
        try:
            context = review.fetch_pr_context({"repo": "atzmonpersonalassistant/trader"}, 7, "token")
        finally:
            review.github_request = original
        self.assertEqual([label["name"] for label in context["pr"]["labels"]], ["human:approved"])
        self.assertTrue(any("/issues/7" in url for _, url, _ in calls))

    def test_review_required_check_fails_when_model_review_missing(self):
        review = load("trading_review_agent", "tools/trading_review_agent.py")
        with TemporaryDirectory() as tmp:
            path, text, passed = review.write_review(
                Path(tmp),
                9,
                {"pass": True, "findings": [], "checklist": []},
                {"returncode": 1, "stdout": "", "stderr": "redacted"},
            )
            _, skipped_text, skipped_passed = review.write_review(
                Path(tmp),
                10,
                {"pass": True, "findings": [], "checklist": []},
                None,
            )
            _, malformed_text, malformed_passed = review.write_review(
                Path(tmp),
                11,
                {"pass": True, "findings": [], "checklist": []},
                {"returncode": 0, "review_text": "Looks okay but missing prefix"},
            )
        self.assertFalse(passed)
        self.assertIn("Model review failed", text)
        self.assertFalse(skipped_passed)
        self.assertIn("Model review was skipped", skipped_text)
        self.assertFalse(malformed_passed)
        self.assertIn("did not start with PASS or FAIL", malformed_text)

    def test_agent_command_timeout_redacts_tokens(self):
        review = load("trading_review_agent", "tools/trading_review_agent.py")
        url_fixture = "https://x-access-token:" + "ghs_TIMEOUTSECRET" + "@github.com/owner/repo.git"
        result = review.run_cmd(["python3", "-c", "import time,sys; print(sys.argv[1]); time.sleep(2)", url_fixture], timeout=0.1)
        rendered = " ".join(result["command"]) + result["stdout"] + result["stderr"]
        self.assertEqual(result["returncode"], 124)
        self.assertNotIn("ghs_TIMEOUTSECRET", rendered)
        self.assertIn("Command timed out", rendered)

    def test_agent_command_results_redact_github_installation_tokens(self):
        review = load("trading_review_agent", "tools/trading_review_agent.py")
        coding = load("trading_coding_agent", "tools/trading_coding_agent.py")
        url_fixture = "https://x-access-token:" + "ghs_ABC123SECRET" + "@github.com/owner/repo.git"
        result = review.run_cmd(["python3", "-c", "import sys; print(sys.argv[1]); print(sys.argv[1], file=sys.stderr)", url_fixture])
        rendered = " ".join(result["command"]) + result["stdout"] + result["stderr"]
        self.assertIn("<redacted>", rendered)
        self.assertNotIn("ghs_ABC123SECRET", rendered)
        self.assertNotIn("ghs_ABC123SECRET", " ".join(coding.redact_command([url_fixture])) + coding.redact_text(url_fixture))

    def test_review_secret_detector_allows_secret_path_docs_but_blocks_literal_key(self):
        review = load("trading_review_agent", "tools/trading_review_agent.py")
        safe = review.deterministic_review({
            "diff": "+Private keys are stored under /etc/trading-agents/secrets/<role>/private-key.pem\n",
            "pr": {"labels": [{"name": "human:approved"}]},
        })
        self.assertTrue(safe["pass"])
        workflow_reference = review.deterministic_review({
            "diff": "+VPS_SSH_PRIVATE_KEY: ${{ secrets.VPS_SSH_PRIVATE_KEY }}\n",
            "pr": {"labels": [{"name": "human:approved"}]},
        })
        self.assertTrue(workflow_reference["pass"])

        begin_marker = "-----BEGIN " + "PRIVATE KEY-----"
        end_marker = "-----END " + "PRIVATE KEY-----"
        self.assertEqual(review.redact_text(begin_marker + "\nabc\n" + end_marker), "<private-key-redacted>")
        unsafe = review.deterministic_review({
            "diff": "+" + begin_marker + "\n+abc\n+" + end_marker + "\n",
            "pr": {"labels": []},
        })
        self.assertFalse(unsafe["pass"])

        fake_github_token = "ghp_" + "abcdefghijklmnopqrstuvwxyz123456"
        fake_openai_token = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
        token_unsafe = review.deterministic_review({
            "diff": f"+GITHUB_TOKEN={fake_github_token}\n+OPENAI_API_KEY={fake_openai_token}\n",
            "pr": {"labels": []},
        })
        self.assertFalse(token_unsafe["pass"])
        literal_value = "literal" + "_secret" + "_value"
        lowercase_unsafe = review.deterministic_review({
            "diff": f"+password={literal_value}\n+api_key={literal_value}\n",
            "pr": {"labels": []},
        })
        self.assertFalse(lowercase_unsafe["pass"])
        code_safe = review.deterministic_review({
            "diff": "+token = mint_token(config)\n+DEFAULT_TOKEN_CMD = os.environ.get(\"TRADING_AGENT_TOKEN_CMD\")\n",
            "pr": {"labels": []},
        })
        self.assertTrue(code_safe["pass"])
        self.assertFalse(review.should_run_model_review(token_unsafe, skip_model=False))
        with TemporaryDirectory() as tmp:
            _, review_text, passed = review.write_review(Path(tmp), 13, token_unsafe, None)
        self.assertFalse(passed)
        self.assertIn("raw diff was not sent to the model", review_text)


if __name__ == "__main__":
    unittest.main()
