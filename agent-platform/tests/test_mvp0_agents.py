import argparse
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class MVP0AgentTests(unittest.TestCase):
    def test_bootstrap_new_vps_script_static_validation(self):
        script = ROOT / "agent-platform/scripts/bootstrap-new-vps.sh"
        subprocess.run(["bash", "-n", str(script)], check=True)
        text = script.read_text()
        self.assertIn('ca-certificates curl gh git jq nodejs npm openssh-client openssl python3 python3-pip python3-venv sqlite3 sudo', text)
        self.assertIn('npm install -g @openai/codex', text)
        self.assertIn('python3 -m pip install --break-system-packages --upgrade lean', text)
        self.assertIn('usermod -aG agent-coding agent-orchestrator', text)
        self.assertIn('usermod -aG agent-review agent-orchestrator', text)
        self.assertIn('install_dir agent-coding agent-coding 2770 /agents/coding/workspaces', text)
        self.assertIn('install_dir agent-review agent-review 2770 /agents/review/workspaces', text)
        self.assertIn('ensure_user agent-research', text)
        self.assertIn('install_dir agent-research agent-research 750 /agents/research', text)
        self.assertIn('install_dir agent-research agent-research 750 /agents/research/lean-workspace', text)
        self.assertIn('chown -R agent-research:agent-research /agents/research', text)
        self.assertIn('chmod 750 /agents/research /agents/research/state /agents/research/logs /agents/research/reports /agents/research/lean-workspace', text)
        self.assertNotIn('groupadd --system agent-platform', text)
        self.assertIn('install_dir root root 755 /etc/trading-agents', text)
        self.assertIn('install_dir root root 711 /etc/trading-agents/secrets', text)
        self.assertIn('/usr/local/sbin/trading-dispatch-coding-agent *', text)
        self.assertIn('/usr/local/sbin/trading-dispatch-coding-agent-stub *', text)
        self.assertNotIn('NOPASSWD: /usr/local/bin/trading-coding-agent *', text)
        self.assertIn('for role in orchestrator coding review validator research; do', text)
        self.assertIn('"orchestrator": {', text)
        self.assertIn('"coding": {', text)
        self.assertIn('"review": {', text)
        self.assertIn('"research": {', text)
        self.assertIn('"linux_user": "agent-research"', text)
        self.assertNotIn('"roles": {', text)
        self.assertIn('install_dir root agent-research 750 /etc/trading-agents/secrets/research', text)
        self.assertIn('groupadd --system agent-quantconnect', text)
        self.assertIn('usermod -aG agent-quantconnect agent-orchestrator', text)
        self.assertIn('usermod -aG agent-quantconnect agent-validator', text)
        self.assertIn('usermod -aG agent-quantconnect agent-research', text)
        self.assertNotIn('usermod -aG agent-quantconnect agent-coding', text)
        self.assertNotIn('usermod -aG agent-quantconnect agent-review', text)
        self.assertIn('install_dir root agent-quantconnect 750 /etc/trading-agents/secrets/quantconnect', text)
        self.assertIn('chmod 640 /etc/trading-agents/secrets/quantconnect/env', text)
        self.assertIn('chmod 644 /etc/trading-agents/github-apps.json', text)
        self.assertIn('chown root:root /etc/trading-agents/github-apps.json', text)

    def test_dispatch_wrappers_reject_unexpected_arguments(self):
        real = ROOT / "agent-platform/tools/trading-dispatch-coding-agent"
        stub = ROOT / "agent-platform/tools/trading-dispatch-coding-agent-stub"
        subprocess.run(["bash", "-n", str(real)], check=True)
        subprocess.run(["bash", "-n", str(stub)], check=True)
        self.assertEqual(subprocess.run([str(real), "--config", "evil"]).returncode, 64)
        self.assertEqual(subprocess.run([str(real), "run", "--issue", "abc"]).returncode, 64)
        self.assertEqual(subprocess.run([str(real), "run", "--issue", "1", "--config", "evil"]).returncode, 64)
        self.assertEqual(subprocess.run([str(stub), "run", "--issue", "1"]).returncode, 64)

    def test_research_agent_seeds_cheap_call_queue(self):
        research = load("trading_research_agent", "agent-platform/tools/trading_research_agent.py")
        with TemporaryDirectory() as tmp:
            queue = Path(tmp) / "strategy-queue.json"
            rc = research.cmd_seed(argparse.Namespace(queue=str(queue)))
            self.assertEqual(rc, 0)
            items = research.load_queue(queue)
            self.assertGreaterEqual(len(items), 3)
            self.assertEqual(items[0]["id"], "qqq-pullback-low-debit-bull-call-spread")
            self.assertEqual(items[0]["status"], "queued")
            self.assertIn("quantconnect_test_spec", items[0])
            self.assertIn(items[0]["family"], {"bull_call_spread", "long_call"})

    def test_research_agent_next_returns_highest_priority_candidate(self):
        research = load("trading_research_agent_next", "agent-platform/tools/trading_research_agent.py")
        with TemporaryDirectory() as tmp:
            queue = Path(tmp) / "strategy-queue.json"
            research.cmd_seed(argparse.Namespace(queue=str(queue)))
            import contextlib
            import io
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = research.cmd_next(argparse.Namespace(queue=str(queue)))
            self.assertEqual(rc, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["type"], "candidate")
            self.assertEqual(payload["candidate"]["id"], "qqq-pullback-low-debit-bull-call-spread")

    def test_research_agent_qc_prompt_is_lean_cloud_diagnostics_first(self):
        research = load("trading_research_agent_prompt", "agent-platform/tools/trading_research_agent.py")
        self.assertIn("Prefer Lean CLI", research.QC_RESEARCH_PROMPT)
        self.assertIn("QuantConnect Cloud", research.QC_RESEARCH_PROMPT)
        self.assertIn("Run diagnostics first", research.QC_RESEARCH_PROMPT)
        self.assertIn("option-chain availability", research.QC_RESEARCH_PROMPT)
        self.assertIn("retest_after_technical_fix", research.QC_RESEARCH_PROMPT)
        self.assertIn("RESEARCH_MANDATE", research.QC_RESEARCH_PROMPT)

    def test_research_agent_mandate_captures_uriel_governance(self):
        research = load("trading_research_agent_mandate", "agent-platform/tools/trading_research_agent.py")
        mandate = research.RESEARCH_MANDATE
        self.assertEqual(mandate["mode"], "autonomous_24_7_within_mandate")
        self.assertIn("options-only", mandate["primary_goal"])
        self.assertEqual(mandate["research_scope"]["instrument_scope"], "Options only. Ignore good non-options/equity-only setups as candidates.")
        self.assertIn("long-premium", mandate["research_scope"]["structure_selection"])
        self.assertIn("defined-risk", mandate["research_scope"]["short_premium"])
        self.assertIn("complexity requires stronger justification", mandate["research_scope"]["complexity_policy"])
        self.assertIn("quick liquidity check", mandate["research_scope"]["liquidity_prefilter"])
        self.assertIn("zero_dte", "_".join(mandate["research_scope"].keys()))
        self.assertIn("2018-present", mandate["candidate_gate"]["candidate_requires_full_validation"])
        self.assertIn("overfitting", mandate["candidate_gate"]["overfitting_policy"])
        self.assertIn("parameter combinations", mandate["candidate_gate"]["parameter_search_disclosure"])
        self.assertIn("overlap/correlation", mandate["candidate_gate"]["correlation_overlap"])
        self.assertEqual(mandate["validation_protocol"]["concurrency"].split(";")[0], "One QC cloud backtest at a time with the current single B2-8 backtest node")
        self.assertIn("No hard daily backtest cap", mandate["validation_protocol"]["daily_cap"])
        self.assertIn("Parameter optimization", mandate["validation_protocol"]["optimization_policy"])
        self.assertIn("bull/bear/sideways", mandate["validation_protocol"]["regime_policy"])
        self.assertIn("data quality", mandate["validation_protocol"]["data_quality_policy"])
        self.assertIn("cheap diagnostics", mandate["validation_protocol"]["runtime_policy"])
        self.assertIn("may not override weak evidence", mandate["validation_protocol"]["llm_judgment_policy"])
        self.assertIn("asymmetric/speculative", mandate["validation_protocol"]["asymmetric_candidate_policy"])
        self.assertTrue(mandate["external_sources"]["citation_required"])
        self.assertIn("GitHub issue", mandate["external_sources"]["tooling_policy"])
        self.assertIn("hourly", mandate["notifications_and_governance"]["heartbeat_frequency"].lower())
        self.assertIn("GitHub issues only", mandate["notifications_and_governance"]["github_permissions"])
        self.assertIn("failure", mandate["notifications_and_governance"]["failure_library"])
        self.assertIn("regular market hours", mandate["notifications_and_governance"]["market_hours_policy"])
        self.assertIn("live_trading", mandate["hard_forbidden"])
        self.assertTrue(mandate["open_questions_next"])

    def test_research_agent_mandate_command_outputs_no_secrets(self):
        research = load("trading_research_agent_mandate_cmd", "agent-platform/tools/trading_research_agent.py")
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = research.cmd_mandate(argparse.Namespace())
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mandate"]["candidate_gate"]["benchmark"], "Primary benchmark is S&P 500 / SPY. Add secondary benchmark when obviously relevant.")
        self.assertNotIn("QUANTCONNECT_API_TOKEN", out.getvalue())
        self.assertNotIn("***", out.getvalue())

    def test_research_agent_lean_setup_plan_has_no_secret_values(self):
        research = load("trading_research_agent_setup", "agent-platform/tools/trading_research_agent.py")
        import contextlib
        import io
        out = io.StringIO()
        args = argparse.Namespace(workspace_dir="/tmp/lean workspace;bad")
        with contextlib.redirect_stdout(out):
            rc = research.cmd_qc_lean_setup_plan(args)
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        commands = "\n".join(payload["commands"])
        self.assertIn("lean login --user-id $QUANTCONNECT_USER_ID", commands)
        self.assertIn("printf '%s\\n'", commands)
        self.assertIn("lean whoami", commands)
        self.assertIn("'/tmp/lean workspace;bad'", commands)
        self.assertNotIn("mkdir -p /tmp/lean workspace;bad", commands)
        self.assertNotIn("/agents/research/lean-workspace", commands)
        self.assertNotIn("--api-token $QUANTCONNECT_API_TOKEN", commands)
        self.assertNotIn("***", commands)

    def test_vps_deploy_logs_lean_in_as_agent_research(self):
        text = (ROOT / ".github/workflows/vps-deploy.yml").read_text()
        self.assertIn("/agents/research/lean-workspace", text)
        self.assertIn("sudo -n -u agent-research bash -lc 'command -v lean >/dev/null 2>&1'", text)
        self.assertIn("python3 -m pip install --break-system-packages --upgrade lean", text)
        self.assertIn("lean login --user-id", text)
        self.assertIn("set -euo pipefail; set -a; . /etc/trading-agents/secrets/quantconnect/env", text)
        self.assertIn("printf \"%s\\n\" \"$QUANTCONNECT_API_TOKEN\" | lean login", text)
        self.assertNotIn("--api-token \"$QUANTCONNECT_API_TOKEN\"", text)
        self.assertIn("lean whoami", text)
        self.assertIn("trading-research-agent --queue /agents/research/state/deploy-smoke-queue.json next", text)

    def test_orchestrator_auto_merge_candidate_requires_agent_label_and_passing_review(self):
        orch = load("trading_orchestrator", "agent-platform/tools/trading_orchestrator.py")
        passing = {"name": "review-agent/pass", "status": "completed", "conclusion": "success", "app": {"slug": "trading-review-agent"}}
        spoofed = {"name": "review-agent/pass", "status": "completed", "conclusion": "success", "app": {"slug": "other-app"}}
        failing = {"name": "review-agent/pass", "status": "completed", "conclusion": "failure", "app": {"slug": "trading-review-agent"}}
        same_repo_pr = {"head": {"ref": "agent/issue-5-docs", "repo": {"full_name": "atzmonpersonalassistant/trader"}}, "base": {"repo": {"full_name": "atzmonpersonalassistant/trader"}}}
        fork_pr = {"head": {"ref": "agent/issue-5-docs", "repo": {"full_name": "evil/fork"}}, "base": {"repo": {"full_name": "atzmonpersonalassistant/trader"}}}
        self.assertEqual(orch.latest_named_check([spoofed, passing], "review-agent/pass", "trading-review-agent"), passing)
        self.assertIsNone(orch.latest_named_check([spoofed], "review-agent/pass", "trading-review-agent"))
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
        agent = load("trading_coding_agent", "agent-platform/tools/trading_coding_agent.py")
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
        agent = load("trading_coding_agent", "agent-platform/tools/trading_coding_agent.py")
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

    def test_orchestrator_clean_status_fallback_merges_and_deletes_branch(self):
        orch = load("trading_orchestrator", "agent-platform/tools/trading_orchestrator.py")
        calls = []

        original_github_request = orch.github_request
        try:
            def fake_github_request(method, url, token, payload=None):
                calls.append((method, url, payload))
                if method == "PUT" and url.endswith("/pulls/8/merge"):
                    return {"merged": True, "sha": "abc"}, {}
                if method == "DELETE" and url.endswith("/git/refs/heads%2Fagent%2Fissue-7-docs"):
                    return None, {}
                raise AssertionError((method, url, payload))

            orch.github_request = fake_github_request
            merge = orch.merge_pull_request("atzmonpersonalassistant", "trader", 8, "token", "reviewed-head-sha")
            deleted = orch.delete_branch_ref("atzmonpersonalassistant", "trader", "agent/issue-7-docs", "token")
        finally:
            orch.github_request = original_github_request

        self.assertEqual(merge, {"merged": True, "sha": "abc"})
        self.assertTrue(deleted)
        self.assertEqual(calls[0][0], "PUT")
        self.assertEqual(calls[0][2]["sha"], "reviewed-head-sha")
        self.assertEqual(calls[1][0], "DELETE")

    def test_orchestrator_dispatch_coding_stub_uses_safe_wrapper_contract(self):
        orch = load("trading_orchestrator_stub_dispatch", "agent-platform/tools/trading_orchestrator.py")
        args = argparse.Namespace(coding_stub_cmd="sudo -n /usr/local/sbin/trading-dispatch-coding-agent-stub")
        cmd = orch.command_parts(args.coding_stub_cmd) + [
            "--issue-number",
            "{issue}",
            "--issue-external-id",
            "{issue_external_id}",
            "--title",
            "{title}",
        ]
        self.assertEqual(cmd[:3], ["sudo", "-n", "/usr/local/sbin/trading-dispatch-coding-agent-stub"])
        self.assertNotIn("run", cmd)

    def test_orchestrator_dispatch_coding_uses_real_agent_command(self):
        orch = load("trading_orchestrator", "agent-platform/tools/trading_orchestrator.py")
        import argparse
        import contextlib
        import io
        import json
        import sqlite3
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.db"
            orch.init_db(db)
            now = orch.now_iso()
            with sqlite3.connect(db) as conn:
                conn.execute("INSERT INTO issues(external_id, number, title, state, labels, payload_json, created_at, updated_at, last_seen_at, retry_count) VALUES ('i21', 21, 'real coding', 'open', ?, '{}', ?, ?, ?, 0)", (json.dumps(["agent:claimed"]), now, now, now))
            calls = []
            class FakeProc:
                returncode = 0
                stdout = "ok"
                stderr = ""
            original = orch.subprocess.run
            def fake_run(cmd, **kwargs):
                calls.append((cmd, kwargs))
                return FakeProc()
            orch.subprocess.run = fake_run
            args = argparse.Namespace(db=db, claimed_label="agent:claimed", coding_agent_cmd="sudo -n /usr/local/sbin/trading-dispatch-coding-agent", timeout_seconds=123)
            try:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    rc = orch.cmd_dispatch_coding(args)
            finally:
                orch.subprocess.run = original
            self.assertEqual(rc, 0)
            self.assertEqual(calls[0][0], ["sudo", "-n", "/usr/local/sbin/trading-dispatch-coding-agent", "run", "--issue", "21"])
            self.assertEqual(calls[0][1]["timeout"], 123)
            result = json.loads(out.getvalue())
            self.assertTrue(result["ok"])
            with sqlite3.connect(db) as conn:
                row = conn.execute("SELECT labels, result_json FROM attempts").fetchone()
            self.assertEqual(json.loads(row[0]), ["coding-agent"])
            self.assertEqual(json.loads(row[1])["command"], ["sudo", "-n", "/usr/local/sbin/trading-dispatch-coding-agent", "run", "--issue", "21"])

    def test_orchestrator_cleanup_workspaces_respects_state_and_dry_run(self):
        orch = load("trading_orchestrator", "agent-platform/tools/trading_orchestrator.py")
        import argparse
        import contextlib
        import io
        import json
        import sqlite3
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "state.db"
            coding = root / "coding"
            review = root / "review"
            (coding / "issue-1").mkdir(parents=True)
            (coding / "issue-2").mkdir(parents=True)
            (review / "pr-3").mkdir(parents=True)
            (review / "pr-4").mkdir(parents=True)
            orch.init_db(db)
            now = orch.now_iso()
            with sqlite3.connect(db) as conn:
                conn.execute("INSERT INTO issues(external_id, number, title, state, labels, payload_json, created_at, updated_at, last_seen_at, retry_count) VALUES ('i1', 1, 'done', 'closed', '[]', '{}', ?, ?, ?, 0)", (now, now, now))
                conn.execute("INSERT INTO issues(external_id, number, title, state, labels, payload_json, created_at, updated_at, last_seen_at, retry_count) VALUES ('i2', 2, 'open', 'open', '[]', '{}', ?, ?, ?, 0)", (now, now, now))
                conn.execute("INSERT INTO pull_requests(external_id, number, issue_external_id, branch, state, labels, payload_json, created_at, updated_at, last_seen_at, retry_count) VALUES ('p3', 3, 'i1', 'agent/issue-1', 'merged', '[]', '{}', ?, ?, ?, 0)", (now, now, now))
                conn.execute("INSERT INTO pull_requests(external_id, number, issue_external_id, branch, state, labels, payload_json, created_at, updated_at, last_seen_at, retry_count) VALUES ('p4', 4, 'i2', 'agent/issue-2', 'open', '[]', '{}', ?, ?, ?, 0)", (now, now, now))
            args = argparse.Namespace(db=db, coding_workspace_root=coding, review_workspace_root=review, older_than_hours=0, confirm_delete=False)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                orch.cmd_cleanup_workspaces(args)
            dry = json.loads(out.getvalue())
            self.assertTrue(dry["dry_run"])
            self.assertTrue((coding / "issue-1").exists())
            self.assertTrue((review / "pr-3").exists())
            self.assertEqual({item.get("issue") for item in dry["cleaned"] if item["kind"] == "coding"}, {1})
            self.assertEqual({item.get("pr") for item in dry["cleaned"] if item["kind"] == "review"}, {3})

            args.confirm_delete = True
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                orch.cmd_cleanup_workspaces(args)
            deleted = json.loads(out.getvalue())
            self.assertFalse((coding / "issue-1").exists())
            self.assertTrue((coding / "issue-2").exists())
            self.assertFalse((review / "pr-3").exists())
            self.assertTrue((review / "pr-4").exists())
            self.assertFalse(deleted["dry_run"])

    def test_orchestrator_notification_outbox_and_ack_sent(self):
        orch = load("trading_orchestrator", "agent-platform/tools/trading_orchestrator.py")
        import argparse
        import contextlib
        import io
        import json
        import sqlite3
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.db"
            orch.init_db(db)
            with sqlite3.connect(db) as conn:
                first = orch.create_notification_outbox(
                    conn,
                    external_id="pr-opened-42",
                    notification_type="pr_opened",
                    message="Agent opened PR #42",
                    payload={"pr": 42, "url": "https://example/pr/42"},
                )
                second = orch.create_notification_outbox(
                    conn,
                    external_id="pr-opened-42",
                    notification_type="pr_opened",
                    message="Agent opened PR #42",
                    payload={"pr": 42},
                )
            self.assertEqual(first, ("pr-opened-42", True))
            self.assertEqual(second, ("pr-opened-42", False))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                orch.cmd_outbox_next(argparse.Namespace(db=db))
            pending = json.loads(out.getvalue())
            self.assertEqual(pending["type"], "pr_opened")
            self.assertEqual(pending["id"], "pr-opened-42")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = orch.cmd_outbox_ack_sent(argparse.Namespace(db=db, outbox_id="pr-opened-42"))
            self.assertEqual(rc, 0)
            with sqlite3.connect(db) as conn:
                state = conn.execute("SELECT state FROM outbox WHERE external_id='pr-opened-42'").fetchone()[0]
            self.assertEqual(state, "sent")

            with sqlite3.connect(db) as conn:
                orch.create_approval_request_outbox(
                    conn,
                    pr_number=43,
                    title="Needs approval",
                    url="https://example/pr/43",
                    reason="human gate",
                    risk_summary="approval must stay pending",
                )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = orch.cmd_outbox_ack_sent(argparse.Namespace(db=db, outbox_id="approval-pr-43"))
            self.assertEqual(rc, 1)
            self.assertEqual(json.loads(out.getvalue())["reason"], "not_notification")
            with sqlite3.connect(db) as conn:
                state = conn.execute("SELECT state FROM outbox WHERE external_id='approval-pr-43'").fetchone()[0]
            self.assertEqual(state, "pending")

            with sqlite3.connect(db) as conn:
                orch.create_blocked_outbox(conn, pr_number=44, title="Blocked", url="https://example/pr/44", reason="retry limit", retry_count=51)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = orch.cmd_outbox_ack_sent(argparse.Namespace(db=db, outbox_id="blocked-pr-44"))
            self.assertEqual(rc, 0)
            with sqlite3.connect(db) as conn:
                state = conn.execute("SELECT state FROM outbox WHERE external_id='blocked-pr-44'").fetchone()[0]
            self.assertEqual(state, "sent")

    def test_orchestrator_blocked_outbox_is_deduped(self):
        orch = load("trading_orchestrator", "agent-platform/tools/trading_orchestrator.py")
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
        agent = load("trading_coding_agent", "agent-platform/tools/trading_coding_agent.py")
        self.assertTrue(agent.is_allowed_mvp0_change("README.md"))
        self.assertTrue(agent.is_allowed_mvp0_change("planning/PROJECT_PLAN.md"))
        self.assertTrue(agent.is_allowed_mvp0_change("planning/ARCHITECTURE.md"))
        self.assertTrue(agent.is_allowed_mvp0_change("planning/docs/quantconnect-agentic-platform-lld.md"))
        self.assertFalse(agent.is_allowed_mvp0_change("agent-platform/docs/mvp0/task-breakdown.md"))
        self.assertFalse(agent.is_allowed_mvp0_change("agent-platform/tools/trading_orchestrator.py"))
        self.assertFalse(agent.is_allowed_mvp0_change(".env"))

    def test_coding_agent_skip_codex_writes_current_planning_path(self):
        agent = load("trading_coding_agent", "agent-platform/tools/trading_coding_agent.py")
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            target = workspace / "planning" / "PROJECT_PLAN.md"
            target.parent.mkdir(parents=True)
            target.write_text("# Project Plan\n", encoding="utf-8")
            result = agent.run_codex(
                workspace,
                {"number": 55, "title": "Smoke"},
                {},
                argparse.Namespace(log_dir=workspace / "logs", skip_codex=True, codex_timeout_seconds=1),
            )
            self.assertEqual(result["returncode"], 0)
            self.assertIn("coding-agent smoke issue #55", target.read_text(encoding="utf-8"))

    def test_review_fetch_pr_context_uses_issue_labels(self):
        review = load("trading_review_agent", "agent-platform/tools/trading_review_agent.py")
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

    def test_vps_deploy_installs_quantconnect_secret_env(self):
        workflow = (ROOT / ".github/workflows/vps-deploy.yml").read_text()
        self.assertIn("QUANTCONNECT_USER_ID: ${{ secrets.QUANTCONNECT_USER_ID }}", workflow)
        self.assertIn("QUANTCONNECT_API_TOKEN: ${{ secrets.QUANTCONNECT_API_TOKEN }}", workflow)
        self.assertIn('printf "QUANTCONNECT_USER_ID=%q\\n" "$QUANTCONNECT_USER_ID"', workflow)
        self.assertIn('printf "QUANTCONNECT_API_TOKEN=%q\\n" "$QUANTCONNECT_API_TOKEN"', workflow)
        self.assertIn('sudo groupadd --system agent-quantconnect', workflow)
        self.assertIn('sudo usermod -aG agent-quantconnect agent-orchestrator', workflow)
        self.assertIn('sudo usermod -aG agent-quantconnect agent-validator', workflow)
        self.assertIn('sudo usermod -aG agent-quantconnect agent-research', workflow)
        self.assertIn('sudo useradd --system --create-home --shell /usr/sbin/nologin agent-research', workflow)
        self.assertIn('sudo install -d -o agent-research -g agent-research -m 750 /agents/research /agents/research/state /agents/research/logs /agents/research/reports', workflow)
        self.assertIn('sudo chown -R agent-research:agent-research /agents/research', workflow)
        self.assertIn('/agents/research/state/deploy-smoke-queue.json', workflow)
        self.assertNotIn('sudo usermod -aG agent-quantconnect agent-coding', workflow)
        self.assertNotIn('sudo usermod -aG agent-quantconnect agent-review', workflow)
        self.assertIn('sudo install -d -o root -g agent-quantconnect -m 750 /etc/trading-agents/secrets/quantconnect', workflow)
        self.assertIn('sudo install -o root -g agent-quantconnect -m 640 "$DEPLOY_DIR/quantconnect.env" /etc/trading-agents/secrets/quantconnect/env', workflow)
        self.assertIn('/etc/trading-agents/secrets/quantconnect/env; test -n "$QUANTCONNECT_USER_ID"; test -n "$QUANTCONNECT_API_TOKEN"', workflow)
        self.assertIn('sudo -n -u agent-research bash -lc', workflow)
        self.assertIn('sudo -n -u agent-research env PYTHONDONTWRITEBYTECODE=1 trading-research-agent', workflow)
        self.assertNotIn('QUANTCONNECT_API_TOKEN=***', workflow)

    def test_review_autoreview_selection_and_required_failure(self):
        review = load("trading_review_agent", "agent-platform/tools/trading_review_agent.py")
        context = {
            "files": [{"filename": ".github/workflows/vps-deploy.yml"}],
            "pr": {"labels": [], "base": {"ref": "main"}},
        }
        deterministic = {"pass": True, "findings": [], "checklist": []}
        model = {"returncode": 0, "review_text": "PASS\nLooks good"}
        self.assertTrue(review.should_run_autoreview(context, {"autoreview_enabled": True, "autoreview_max_changed_files": 12}, deterministic, model, False))
        self.assertFalse(review.should_run_autoreview(context, {"autoreview_enabled": False}, deterministic, model, False))
        self.assertFalse(review.should_run_autoreview(context, {"autoreview_enabled": True}, {"pass": False}, model, False))
        with TemporaryDirectory() as tmp:
            _, text, passed = review.write_review(
                Path(tmp),
                22,
                deterministic,
                model,
                {"returncode": 1, "stdout": "finding", "stderr": "", "command": ["autoreview"]},
                True,
            )
        self.assertFalse(passed)
        self.assertIn("Result: FAIL", text)
        self.assertIn("## Autoreview", text)
        self.assertIn("FAIL", text)

    def test_review_required_check_fails_when_model_review_missing(self):
        review = load("trading_review_agent", "agent-platform/tools/trading_review_agent.py")
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
        review = load("trading_review_agent", "agent-platform/tools/trading_review_agent.py")
        url_fixture = "https://x-access-token:" + "ghs_TIMEOUTSECRET" + "@github.com/owner/repo.git"
        result = review.run_cmd(["python3", "-c", "import time,sys; print(sys.argv[1]); time.sleep(2)", url_fixture], timeout=0.1)
        rendered = " ".join(result["command"]) + result["stdout"] + result["stderr"]
        self.assertEqual(result["returncode"], 124)
        self.assertNotIn("ghs_TIMEOUTSECRET", rendered)
        self.assertIn("Command timed out", rendered)

    def test_token_helper_enforces_role_linux_user(self):
        token = load("trading_agent_token", "agent-platform/tools/trading_agent_token.py")
        self.assertEqual(token.expected_linux_user("coding", {}), "agent-coding")
        self.assertEqual(token.expected_linux_user("coding", {"linux_user": "custom-coder"}), "custom-coder")
        class FakePw:
            pw_name = "agent-review"

        original_geteuid = token.os.geteuid
        original_getpwuid = token.pwd.getpwuid
        token.os.geteuid = lambda: 123
        token.pwd.getpwuid = lambda uid: FakePw()
        try:
            with self.assertRaises(SystemExit):
                token.enforce_role_user("coding", {})
            token.enforce_role_user("review", {})
        finally:
            token.os.geteuid = original_geteuid
            token.pwd.getpwuid = original_getpwuid

    def test_agent_command_results_redact_github_installation_tokens(self):
        review = load("trading_review_agent", "agent-platform/tools/trading_review_agent.py")
        coding = load("trading_coding_agent", "agent-platform/tools/trading_coding_agent.py")
        url_fixture = "https://x-access-token:" + "ghs_ABC123SECRET" + "@github.com/owner/repo.git"
        result = review.run_cmd(["python3", "-c", "import sys; print(sys.argv[1]); print(sys.argv[1], file=sys.stderr)", url_fixture])
        rendered = " ".join(result["command"]) + result["stdout"] + result["stderr"]
        self.assertIn("<redacted>", rendered)
        self.assertNotIn("ghs_ABC123SECRET", rendered)
        self.assertNotIn("ghs_ABC123SECRET", " ".join(coding.redact_command([url_fixture])) + coding.redact_text(url_fixture))

    def test_review_secret_detector_allows_secret_path_docs_but_blocks_literal_key(self):
        review = load("trading_review_agent", "agent-platform/tools/trading_review_agent.py")
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
