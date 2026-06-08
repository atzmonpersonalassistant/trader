import importlib.util
import unittest
from pathlib import Path

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
        self.assertEqual(orch.is_auto_merge_candidate(["agent:pr-opened"], passing), (True, "ok"))
        self.assertEqual(orch.is_auto_merge_candidate([], passing), (False, "missing_agent_pr_opened"))
        self.assertEqual(orch.is_auto_merge_candidate(["agent:pr-opened", "agent:needs-fix"], passing), (False, "needs_fix"))
        self.assertEqual(orch.is_auto_merge_candidate(["agent:pr-opened"], failing), (False, "review_not_successful"))
        self.assertEqual(orch.is_auto_merge_candidate(["agent:pr-opened"], None), (False, "missing_review_check"))

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

    def test_review_agent_redacts_github_installation_tokens(self):
        review = load("trading_review_agent", "tools/trading_review_agent.py")
        result = review.run_cmd([
            "python3",
            "-c",
            "print('ok')",
            "https://x-access-token:ghs_ABC123SECRET@github.com/owner/repo.git",
        ])
        rendered = " ".join(result["command"])
        self.assertIn("x-access-token:***@github.com", rendered)
        self.assertNotIn("ghs_ABC123SECRET", rendered)

    def test_review_secret_detector_allows_secret_path_docs_but_blocks_literal_key(self):
        review = load("trading_review_agent", "tools/trading_review_agent.py")
        safe = review.deterministic_review({
            "diff": "+Private keys are stored under /etc/trading-agents/secrets/<role>/private-key.pem\n",
            "pr": {"labels": [{"name": "human:approved"}]},
        })
        self.assertTrue(safe["pass"])

        unsafe = review.deterministic_review({
            "diff": "+-----BEGIN PRIVATE KEY-----\n+abc\n+-----END PRIVATE KEY-----\n",
            "pr": {"labels": []},
        })
        self.assertFalse(unsafe["pass"])


if __name__ == "__main__":
    unittest.main()
