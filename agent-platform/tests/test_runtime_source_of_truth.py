from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/vps-deploy.yml"
RUNTIME = ROOT / "agent-platform/runtime"


class RuntimeSourceOfTruthTest(unittest.TestCase):
    def test_runtime_files_are_versioned_and_installed(self) -> None:
        workflow = WORKFLOW.read_text()
        expected = [
            "agent-platform/runtime/bin/trading-research-runner-codex",
            "agent-platform/runtime/bin/trading-research-watchdog-codex",
            "agent-platform/runtime/bin/trading-workspace-cleanup",
            "agent-platform/runtime/systemd/trading-orchestrator.service",
            "agent-platform/runtime/systemd/trading-orchestrator.timer",
            "agent-platform/runtime/systemd/trading-research-agent.service",
            "agent-platform/runtime/systemd/trading-workspace-cleanup.service",
            "agent-platform/runtime/systemd/trading-workspace-cleanup.timer",
            "agent-platform/runtime/systemd/trader-earnings-otm-daily.service",
            "agent-platform/runtime/systemd/trader-earnings-otm-daily.timer",
            "agent-platform/runtime/systemd/trader-earnings-llm-postrun.service",
            "agent-platform/runtime/systemd/trader-earnings-llm-postrun.timer",
            "agent-platform/runtime/systemd/trader-earnings-llm-watchdog.service",
            "agent-platform/runtime/systemd/trader-earnings-llm-watchdog.timer",
            "agent-platform/runtime/systemd/trader-research-retention.service",
            "agent-platform/runtime/systemd/trader-research-retention.timer",
        ]
        for rel in expected:
            with self.subTest(rel=rel):
                self.assertTrue((ROOT / rel).exists(), rel)
                self.assertIn(rel, workflow)
                self.assertIn(f'"$DEPLOY_DIR/{pathlib.Path(rel).name}"', workflow)

    def test_deploy_workflow_does_not_inline_runtime_helpers_or_units(self) -> None:
        workflow = WORKFLOW.read_text()
        forbidden = [
            "sudo tee /usr/local/bin/trading-research-runner-codex >/dev/null <<",
            "sudo tee /usr/local/bin/trading-research-watchdog-codex >/dev/null <<",
            "sudo tee /usr/local/bin/trading-workspace-cleanup >/dev/null <<",
            "sudo tee /etc/systemd/system/trading-orchestrator.service >/dev/null <<",
            "sudo tee /etc/systemd/system/trading-orchestrator.timer >/dev/null <<",
            "sudo tee /etc/systemd/system/trading-research-agent.service >/dev/null <<",
            "sudo tee /etc/systemd/system/trading-workspace-cleanup.service >/dev/null <<",
            "sudo tee /etc/systemd/system/trading-workspace-cleanup.timer >/dev/null <<",
            "sudo tee /etc/systemd/system/trader-earnings-otm-daily.service >/dev/null <<",
            "sudo tee /etc/systemd/system/trader-earnings-otm-daily.timer >/dev/null <<",
            "sudo tee /etc/systemd/system/trader-earnings-llm-postrun.service >/dev/null <<",
            "sudo tee /etc/systemd/system/trader-earnings-llm-postrun.timer >/dev/null <<",
            "sudo tee /etc/systemd/system/trader-earnings-llm-watchdog.service >/dev/null <<",
            "sudo tee /etc/systemd/system/trader-earnings-llm-watchdog.timer >/dev/null <<",
            "sudo tee /etc/systemd/system/trader-research-retention.service >/dev/null <<",
            "sudo tee /etc/systemd/system/trader-research-retention.timer >/dev/null <<",
        ]
        for snippet in forbidden:
            with self.subTest(snippet=snippet):
                self.assertNotIn(snippet, workflow)

    def test_runtime_shell_files_pass_bash_parse(self) -> None:
        # This is a lightweight source-of-truth guard; the deploy smoke still validates installed files.
        shell_files = list((RUNTIME / "bin").glob("*"))
        self.assertTrue(shell_files)
        for path in shell_files:
            text = path.read_text()
            self.assertTrue(text.startswith("#!/usr/bin/env bash"), path)
            self.assertNotRegex(text, re.compile(r"QUANTCONNECT_API_TOKEN=.+"), path)


if __name__ == "__main__":
    unittest.main()
