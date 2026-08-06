from pathlib import Path
import json
import os
import subprocess
from tempfile import TemporaryDirectory
import textwrap
import unittest


WORKFLOW = Path('.github/workflows/vps-deploy.yml')


def workflow_text():
    return WORKFLOW.read_text()


def deploy_run_script():
    text = workflow_text()
    marker = '      - name: Install tools and verify'
    start = text.index(marker)
    run_start = text.index('        run: |', start)
    next_step = text.find('\n      - name:', run_start + 1)
    block = text[run_start:].splitlines()[1:] if next_step == -1 else text[run_start:next_step].splitlines()[1:]
    return '\n'.join(line[10:] if line.startswith('          ') else line for line in block)


def extract_restart_guard(script):
    lines = script.splitlines()
    start = next(i for i, line in enumerate(lines) if 'command -v systemctl' in line and 'trading-research-agent.service' in line)
    end = next(i for i in range(start, len(lines)) if lines[i] == 'fi')
    return '\n'.join(lines[start:end + 1]) + '\n'


def extract_deploy_ok_check(script):
    lines = script.splitlines()
    remote_end = lines.index('REMOTE')
    return '\n'.join(lines[remote_end + 1:remote_end + 2]) + '\n'


class VpsDeployWorkflowTests(unittest.TestCase):

    def test_earnings_research_has_single_public_cli(self):
        workflow = workflow_text()

        self.assertIn('/agents/research/bin/earnings-qc-research', workflow)
        self.assertIn('/agents/research/libexec/earnings-qc-options/earnings-qc-options-scan', workflow)
        self.assertIn('/agents/research/libexec/earnings-qc-options/earnings-qc-multiyear-backtest', workflow)
        self.assertIn('/agents/research/libexec/earnings-qc-options/earnings-qc-classify-bounded-action', workflow)
        self.assertNotIn('agent-platform/scripts/earnings-qc-options/earnings-qc-daily-run.sh', workflow)
        self.assertIn('sudo rm -f /usr/local/bin/earnings-qc-daily-run.sh /usr/local/bin/earnings-otm-daily-root.sh', workflow)
        self.assertIn('test ! -e /usr/local/bin/earnings-qc-daily-run.sh', workflow)
        self.assertIn('test ! -e /usr/local/bin/earnings-otm-daily-root.sh', workflow)
        self.assertIn('sudo crontab -l', workflow)
        self.assertIn('/usr/local/bin/earnings-qc-daily-run.sh', workflow)
        self.assertIn('/usr/local/bin/earnings-otm-daily-root.sh', workflow)
        self.assertIn('rm -f /agents/research/bin/earnings-qc-options-full-scan', workflow)
        self.assertIn('test ! -e /agents/research/bin/earnings-qc-options-full-scan', workflow)
        self.assertIn('test ! -e /agents/research/bin/earnings-qc-options-scan', workflow)
        self.assertIn('test ! -e /agents/research/bin/earnings-qc-multiyear-backtest', workflow)
        self.assertNotIn('rm -f /agents/research/bin/earnings-qc-research', workflow)
        self.assertNotIn('agent-platform/scripts/earnings-qc-options/earnings-qc-options-full-scan', workflow)
        self.assertNotIn('/agents/research/bin/earnings-qc-options-scan --help', workflow)
        self.assertNotIn('/agents/research/bin/earnings-qc-options-full-scan --help', workflow)
        self.assertIn('/agents/research/bin/earnings-otm-daily.sh', workflow)
        self.assertIn('export HOME=/home/agent-research', workflow)
        self.assertIn('# BEGIN trader managed daily earnings research', workflow)
        self.assertIn('# END trader managed daily earnings research', workflow)
        self.assertNotIn('CRON_TZ=Asia/Jerusalem', workflow)
        self.assertNotIn('0 6 * * * /agents/research/bin/earnings-otm-daily.sh', workflow)
        self.assertIn('trader-earnings-otm-daily.timer', workflow)
        self.assertIn('OnCalendar=*-*-* 10:30:00 Asia/Jerusalem', workflow)
        self.assertNotIn('Timezone=Asia/Jerusalem', workflow)
        self.assertIn('/agents/research/bin/earnings-llm-postrun-review', workflow)
        self.assertIn('agent-platform/skills/trader-research-system/**', workflow)
        self.assertIn('agent-platform/skills/trader-research-system/SKILL.md', workflow)
        self.assertIn('/agents/research/skills/trader-research-system/SKILL.md', workflow)
        self.assertIn('earnings-llm-postrun-review', workflow)
        self.assertIn('# BEGIN trader managed LLM postrun review', workflow)
        self.assertIn('# END trader managed LLM postrun review', workflow)
        self.assertNotIn('*/5 * * * * /agents/research/bin/earnings-llm-postrun-review', workflow)
        self.assertIn('trader-earnings-llm-postrun.timer', workflow)
        self.assertIn('OnCalendar=*-*-* *:0/5:00 Asia/Jerusalem', workflow)
        self.assertNotIn('*/30 * * * * /agents/research/bin/earnings-llm-postrun-review', workflow)
        self.assertIn('llm-postrun-review.log', workflow)
        self.assertIn('earnings-llm-research-watchdog', workflow)
        self.assertIn('# BEGIN trader managed LLM research watchdog', workflow)
        self.assertIn('# END trader managed LLM research watchdog', workflow)
        self.assertNotIn('*/15 * * * * /agents/research/bin/earnings-llm-research-watchdog', workflow)
        self.assertIn('trader-earnings-llm-watchdog.timer', workflow)
        self.assertIn('OnCalendar=*-*-* *:0/15:00 Asia/Jerusalem', workflow)
        self.assertIn('EARNINGS_POSTRUN_DAILY_RUN_SCHEDULED_AT=10:30', workflow)
        self.assertIn('EARNINGS_WATCHDOG_DAILY_SCHEDULE=10:30', workflow)
        self.assertIn('EARNINGS_WATCHDOG_DAILY_SCHEDULE_ZONE=Asia/Jerusalem', workflow)
        self.assertIn('llm-research-watchdog.log', workflow)
        self.assertNotIn('earnings-llm-postrun-review || true', workflow)
        self.assertIn('DAILY_RUN_LOCK_CONTENDED lock=$LOCK holder=$holder', workflow)
        self.assertIn('holder="$(fuser "$LOCK"', workflow)
        self.assertNotIn('flock -n 9 || exit 0', workflow)
        self.assertIn('earnings-qc-research run', workflow)
        self.assertIn('--campaign "$CAMPAIGN"', workflow)
        self.assertIn(r'/^0 9 \* \* \* \/agents\/research\/bin\/earnings-otm-daily\.sh$/ {next}', workflow)
        self.assertNotIn("'0 9 * * * /agents/research/bin/earnings-otm-daily.sh'", workflow)
        self.assertNotIn('earnings-qc-options-scan run-now', workflow)

    def test_managed_earnings_timers_are_verified(self):
        workflow = workflow_text()

        self.assertIn('systemctl daemon-reload', workflow)
        self.assertIn('systemctl enable --now trader-earnings-otm-daily.timer trader-earnings-llm-postrun.timer trader-earnings-llm-watchdog.timer trader-research-retention.timer', workflow)
        self.assertIn("systemctl cat trader-earnings-otm-daily.timer | grep -q 'OnCalendar=\\*-\\*-\\* 10:30:00 Asia/Jerusalem'", workflow)
        self.assertIn("systemctl cat trader-earnings-llm-postrun.timer | grep -q 'OnCalendar=\\*-\\*-\\* \\*:0/5:00 Asia/Jerusalem'", workflow)
        self.assertIn("systemctl cat trader-earnings-llm-watchdog.timer | grep -q 'OnCalendar=\\*-\\*-\\* \\*:0/15:00 Asia/Jerusalem'", workflow)
        self.assertIn('systemctl is-enabled --quiet trader-earnings-otm-daily.timer', workflow)
        self.assertIn('systemctl is-enabled --quiet trader-earnings-llm-postrun.timer', workflow)
        self.assertIn('systemctl is-enabled --quiet trader-earnings-llm-watchdog.timer', workflow)

    def test_managed_research_retention_timer_is_verified(self):
        workflow = workflow_text()

        self.assertIn('trader-research-retention.service', workflow)
        self.assertIn('trader-research-retention.timer', workflow)
        self.assertIn('OnCalendar=*-*-* 04:15:00 Asia/Jerusalem', workflow)
        self.assertIn('earnings-qc-research cleanup --older-than-days 14 --keep-last 20', workflow)
        self.assertIn('docker image prune -f --filter until=168h', workflow)
        self.assertIn('docker image prune requires root-owned Docker socket access', workflow)
        self.assertIn("systemctl cat trader-research-retention.timer | grep -q 'OnCalendar=\\*-\\*-\\* 04:15:00 Asia/Jerusalem'", workflow)
        self.assertIn("systemctl cat trader-research-retention.service | grep -q 'earnings-qc-research cleanup --older-than-days 14 --keep-last 20'", workflow)
        self.assertIn("systemctl cat trader-research-retention.service | grep -q 'docker image prune -f --filter until=168h'", workflow)
        self.assertIn('systemctl is-enabled --quiet trader-research-retention.timer', workflow)
        self.assertNotIn('docker system prune', workflow)
        self.assertNotIn('docker volume prune', workflow)

    def _daily_wrapper_script(self, root, fake_bin, state, logs, reports):
        script = deploy_run_script()
        start = script.index("sudo tee /agents/research/bin/earnings-otm-daily.sh")
        heredoc_start = script.index("<<'EOF_DAILY_EARNINGS'", start)
        body_start = script.index("\n", heredoc_start) + 1
        body_end = script.index("\nEOF_DAILY_EARNINGS", body_start)
        daily = "\n".join(
            line[10:] if line.startswith("          ") else line
            for line in script[body_start:body_end].splitlines()
        )
        daily_path = root / "earnings-otm-daily.sh"
        daily_path.write_text(
            daily.replace("/agents/research/state/earnings-qc-research", str(state))
            .replace("/agents/research/logs/earnings-qc-research", str(logs))
            .replace("/agents/research/reports", str(reports))
            .replace("export PATH=/agents/research/bin:/usr/local/bin:/usr/bin:/bin", f"export PATH={fake_bin}:/usr/bin:/bin")
        )
        daily_path.chmod(0o755)
        return daily_path

    def _daily_log_text(self, logs):
        matches = [path for path in logs.glob("daily-*.log") if "-attempt-" not in path.name]
        self.assertEqual(len(matches), 1)
        return matches[0].read_text()

    def test_daily_wrapper_retries_lock_contention_once_then_fails(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = root / "bin"
            state = root / "state"
            logs = root / "logs"
            reports = root / "reports"
            fake_bin.mkdir()
            state.mkdir()
            logs.mkdir()
            reports.mkdir()
            daily_path = self._daily_wrapper_script(root, fake_bin, state, logs, reports)
            (fake_bin / "flock").write_text("#!/usr/bin/env bash\nexit 1\n")
            (fake_bin / "fuser").write_text("#!/usr/bin/env bash\nprintf ' 1234 5678\\n'\n")
            (fake_bin / "sleep").write_text("#!/usr/bin/env bash\nexit 0\n")
            for name in ("date", "tr", "sed", "mkdir"):
                target = fake_bin / name
                target.symlink_to(f"/bin/{name}")
            for name in ("earnings-qc-research",):
                (fake_bin / name).write_text("#!/usr/bin/env bash\nexit 99\n")
            for path in fake_bin.iterdir():
                if not path.is_symlink():
                    path.chmod(0o755)

            result = subprocess.run(
                [str(daily_path)],
                env={**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"},
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 75)
            log_text = self._daily_log_text(logs)
            self.assertIn("DAILY_RUN_LOCK_CONTENDED", log_text)
            self.assertIn("DAILY_RUN_RETRY_SLEEP", log_text)
            self.assertIn("DAILY_RUN_RETRY_EXHAUSTED", log_text)
            self.assertIn("lock=", log_text)
            self.assertIn("holder=1234 5678", log_text)
            retry_state = json.loads(next(state.glob("daily-retry-*.json")).read_text())
            self.assertEqual(retry_state["attempt_count"], 2)

    def test_daily_wrapper_terminal_no_candidate_rc_two_is_systemd_success(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = root / "bin"
            state = root / "state"
            logs = root / "logs"
            reports = root / "reports"
            fake_bin.mkdir()
            state.mkdir()
            logs.mkdir()
            reports.mkdir()
            daily_path = self._daily_wrapper_script(root, fake_bin, state, logs, reports)
            (fake_bin / "flock").write_text("#!/usr/bin/env bash\nexit 0\n")
            (fake_bin / "fuser").write_text("#!/usr/bin/env bash\nexit 0\n")
            (fake_bin / "sleep").write_text("#!/usr/bin/env bash\nexit 0\n")
            (fake_bin / "earnings-qc-research").write_text(textwrap.dedent("""\
                #!/usr/bin/env bash
                printf '{"ok": false, "status": "NO_FINAL_CANDIDATES_AFTER_HISTORICAL_OPTION_PNL"}\n'
                exit 2
            """))
            for name in ("date", "tr", "sed", "mkdir"):
                target = fake_bin / name
                target.symlink_to(f"/bin/{name}")
            for path in fake_bin.iterdir():
                if not path.is_symlink():
                    path.chmod(0o755)

            result = subprocess.run(
                [str(daily_path)],
                env={**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin", "EARNINGS_DAILY_RETRY_DELAY_SECONDS": "0"},
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            log_text = self._daily_log_text(logs)
            self.assertIn("classification=terminal", log_text)
            self.assertNotIn("DAILY_RUN_RETRY_SLEEP", log_text)

    def test_daily_wrapper_retries_data_availability_once(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = root / "bin"
            state = root / "state"
            logs = root / "logs"
            reports = root / "reports"
            fake_bin.mkdir()
            state.mkdir()
            logs.mkdir()
            reports.mkdir()
            daily_path = self._daily_wrapper_script(root, fake_bin, state, logs, reports)
            (fake_bin / "flock").write_text("#!/usr/bin/env bash\nexit 0\n")
            (fake_bin / "fuser").write_text("#!/usr/bin/env bash\nexit 0\n")
            (fake_bin / "sleep").write_text("#!/usr/bin/env bash\nexit 0\n")
            counter = root / "counter"
            (fake_bin / "earnings-qc-research").write_text(textwrap.dedent(f"""\
                #!/usr/bin/env bash
                count="$(cat {counter} 2>/dev/null || printf 0)"
                count="$((count + 1))"
                printf '%s' "$count" > {counter}
                if [ "$count" -eq 1 ]; then
                  printf '{{"ok": false, "status": "BLOCKED_QC_CLOUD_NO_SPARE_NODES", "blocked_reason": "QC Cloud has no spare nodes available for a new backtest"}}\n'
                  exit 2
                fi
                printf '{{"ok": true, "status": "OK_FULL_QC_SCAN", "final_candidate_count": 1}}\n'
                exit 0
            """))
            for name in ("date", "tr", "sed", "mkdir"):
                target = fake_bin / name
                target.symlink_to(f"/bin/{name}")
            for path in fake_bin.iterdir():
                if not path.is_symlink():
                    path.chmod(0o755)

            result = subprocess.run(
                [str(daily_path)],
                env={**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin", "EARNINGS_DAILY_RETRY_DELAY_SECONDS": "0"},
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(counter.read_text(), "2")
            log_text = self._daily_log_text(logs)
            self.assertIn("classification=retryable", log_text)
            self.assertIn("DAILY_RUN_RETRY_SLEEP", log_text)
            self.assertIn("attempt=2", log_text)

    def test_research_postgres_cache_db_is_provisioned(self):
        workflow = workflow_text()

        self.assertIn('postgresql postgresql-client', workflow)
        self.assertIn('systemctl enable --now postgresql', workflow)
        self.assertIn('CREATE ROLE "agent-research" LOGIN', workflow)
        self.assertIn('createdb -O "agent-research" trader_research', workflow)
        self.assertIn('CREATE SCHEMA IF NOT EXISTS earnings_cache AUTHORIZATION "agent-research"', workflow)
        self.assertIn('ALTER DATABASE trader_research SET search_path TO earnings_cache, public', workflow)
        self.assertIn('SELECT 1 AS research_postgres_ready', workflow)

    def test_llm_postrun_has_bounded_execution_wrapper(self):
        workflow = workflow_text()
        bootstrap = Path('agent-platform/scripts/bootstrap-new-vps.sh').read_text()
        wrapper = Path('agent-platform/scripts/earnings-qc-options/trading-research-bounded-earnings-qc').read_text()
        postrun = Path('agent-platform/scripts/earnings-qc-options/earnings-llm-postrun-review').read_text()

        self.assertIn('trading-research-bounded-earnings-qc --help', workflow)
        self.assertNotIn('trading-research-bounded-earnings-qc status --pretty', workflow)
        self.assertIn('EARNINGS_DIR="${SCRIPTS_DIR}/earnings-qc-options"', bootstrap)

        for text in (workflow, bootstrap):
            self.assertIn('trading-research-bounded-earnings-qc', text)
            self.assertIn('agent-research-runner ALL=(agent-research) NOPASSWD: /usr/local/sbin/trading-research-bounded-earnings-qc *', text)

        self.assertIn('bounded_action_request.json', postrun)
        self.assertIn('/usr/local/sbin/trading-research-bounded-earnings-qc --bounded-action-dir __ACTION_DIR__ --bounded-action-id __BOUNDED_ACTION_ID__ <argv...>', postrun)
        self.assertIn('no-new-privileges sandbox', postrun)
        self.assertIn('bounded_action_result.json', postrun)
        self.assertIn('runner_pid=host-postrun', postrun)
        self.assertNotIn('REVIEW/RECOMMENDATION ONLY', postrun)
        self.assertNotIn('Do not execute follow-up QC/LEAN/CLI actions', postrun)

        self.assertNotIn('cleanup)', wrapper)
        self.assertIn('--bounded-action-id', wrapper)
        self.assertIn('bounded action id already used', wrapper)
        self.assertIn('bounded action id expired', wrapper)
        self.assertIn('bounded action id output context mismatch', wrapper)
        self.assertIn('bounded action id runner is not active', wrapper)
        self.assertIn('host-postrun', wrapper)
        self.assertIn('bounded action id file ownership invalid', wrapper)
        self.assertIn('bounded action id file mode invalid', wrapper)
        self.assertIn('resolved run-dir outside approved research roots', wrapper)
        self.assertIn('run-dir must not be a symlink or alias', wrapper)
        self.assertIn('--not*', wrapper)
        self.assertIn('run --years must be 1..2', wrapper)
        self.assertIn('historical must be scoped by --run-dir', wrapper)
        self.assertIn('summarize must be scoped by --run-dir', wrapper)
        self.assertNotIn('--run-id) safe_id', wrapper)
        self.assertIn('ordinary bounded experiments may change exactly one knob', wrapper)
        self.assertIn('symbols must be 1-5 uppercase tickers', wrapper)

    def test_deploy_restart_guard_only_touches_active_enabled_service(self):
        restart_guard = extract_restart_guard(deploy_run_script())

        with TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            log_path = bin_dir / 'calls.log'
            (bin_dir / 'systemctl').write_text(textwrap.dedent(f"""\
                #!/usr/bin/env bash
                echo "systemctl $*" >> {log_path}
                case "$1" in
                  is-enabled) exit "${{SYSTEMCTL_ENABLED_RC:-1}}" ;;
                  is-active) exit "${{SYSTEMCTL_ACTIVE_RC:-1}}" ;;
                  *) exit 0 ;;
                esac
            """))
            (bin_dir / 'sudo').write_text(textwrap.dedent(f"""\
                #!/usr/bin/env bash
                echo "sudo $*" >> {log_path}
            """))
            os.chmod(bin_dir / 'systemctl', 0o755)
            os.chmod(bin_dir / 'sudo', 0o755)

            env = {**os.environ, 'PATH': f"{bin_dir}:{os.environ['PATH']}", 'SYSTEMCTL_ENABLED_RC': '0', 'SYSTEMCTL_ACTIVE_RC': '1'}
            subprocess.run(['bash', '-euo', 'pipefail', '-c', restart_guard], env=env, check=True)
            self.assertNotIn('sudo systemctl', log_path.read_text())

            log_path.write_text('')
            env['SYSTEMCTL_ACTIVE_RC'] = '0'
            subprocess.run(['bash', '-euo', 'pipefail', '-c', restart_guard], env=env, check=True)
            self.assertEqual(log_path.read_text().splitlines()[-1], 'sudo systemctl try-restart trading-research-agent.service')

    def test_deploy_requires_remote_deploy_ok_sentinel(self):
        deploy_ok_check = extract_deploy_ok_check(deploy_run_script())

        with TemporaryDirectory() as tmp:
            output = Path(tmp) / 'deploy-output.log'
            env = {**os.environ, 'deploy_output': str(output)}
            output.write_text('partial output without sentinel\n')
            missing = subprocess.run(['bash', '-euo', 'pipefail', '-c', deploy_ok_check], env=env)
            self.assertNotEqual(missing.returncode, 0)

            output.write_text('setup complete\nDEPLOY_OK\n')
            present = subprocess.run(['bash', '-euo', 'pipefail', '-c', deploy_ok_check], env=env)
            self.assertEqual(present.returncode, 0)


if __name__ == '__main__':
    unittest.main()
