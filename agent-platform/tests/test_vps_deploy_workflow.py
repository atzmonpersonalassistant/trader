from pathlib import Path
import unittest


class VpsDeployWorkflowTests(unittest.TestCase):

    def test_earnings_research_has_single_public_cli(self):
        workflow = Path('.github/workflows/vps-deploy.yml').read_text()

        self.assertIn('/agents/research/bin/earnings-qc-research', workflow)
        self.assertIn('/agents/research/libexec/earnings-qc-options/earnings-qc-options-scan', workflow)
        self.assertIn('/agents/research/libexec/earnings-qc-options/earnings-qc-multiyear-backtest', workflow)
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
        self.assertIn('0 6 * * * /agents/research/bin/earnings-otm-daily.sh', workflow)
        self.assertIn('/agents/research/bin/earnings-llm-postrun-review', workflow)
        self.assertIn('agent-platform/skills/trader-research-system/**', workflow)
        self.assertIn('agent-platform/skills/trader-research-system/SKILL.md', workflow)
        self.assertIn('/agents/research/skills/trader-research-system/SKILL.md', workflow)
        self.assertIn('earnings-llm-postrun-review', workflow)
        self.assertIn('# BEGIN trader managed LLM postrun review', workflow)
        self.assertIn('# END trader managed LLM postrun review', workflow)
        self.assertIn('*/30 * * * * /agents/research/bin/earnings-llm-postrun-review', workflow)
        self.assertIn('llm-postrun-review.log', workflow)
        self.assertNotIn('earnings-llm-postrun-review || true', workflow)
        self.assertIn('flock -n 9 || exit 0', workflow)
        self.assertIn('earnings-qc-research run', workflow)
        self.assertIn('--campaign daily-earnings-otm', workflow)
        self.assertIn(r'/^0 9 \* \* \* \/agents\/research\/bin\/earnings-otm-daily\.sh$/ {next}', workflow)
        self.assertNotIn("'0 9 * * * /agents/research/bin/earnings-otm-daily.sh'", workflow)
        self.assertNotIn('earnings-qc-options-scan run-now', workflow)

    def test_research_postgres_cache_db_is_provisioned(self):
        workflow = Path('.github/workflows/vps-deploy.yml').read_text()

        self.assertIn('postgresql postgresql-client', workflow)
        self.assertIn('systemctl enable --now postgresql', workflow)
        self.assertIn('CREATE ROLE "agent-research" LOGIN', workflow)
        self.assertIn('createdb -O "agent-research" trader_research', workflow)
        self.assertIn('CREATE SCHEMA IF NOT EXISTS earnings_cache AUTHORIZATION "agent-research"', workflow)
        self.assertIn('ALTER DATABASE trader_research SET search_path TO earnings_cache, public', workflow)
        self.assertIn('SELECT 1 AS research_postgres_ready', workflow)

    def test_llm_postrun_has_bounded_execution_wrapper(self):
        workflow = Path('.github/workflows/vps-deploy.yml').read_text()
        bootstrap = Path('agent-platform/scripts/bootstrap-new-vps.sh').read_text()
        wrapper = Path('agent-platform/scripts/earnings-qc-options/trading-research-bounded-earnings-qc').read_text()
        postrun = Path('agent-platform/scripts/earnings-qc-options/earnings-llm-postrun-review').read_text()

        self.assertIn('trading-research-bounded-earnings-qc --help', workflow)
        self.assertNotIn('trading-research-bounded-earnings-qc status --pretty', workflow)
        self.assertIn('EARNINGS_DIR="${SCRIPTS_DIR}/earnings-qc-options"', bootstrap)

        for text in (workflow, bootstrap):
            self.assertIn('trading-research-bounded-earnings-qc', text)
            self.assertIn('agent-research-runner ALL=(agent-research) NOPASSWD: /usr/local/sbin/trading-research-bounded-earnings-qc *', text)

        self.assertIn('sudo -n -u agent-research /usr/local/sbin/trading-research-bounded-earnings-qc --bounded-action-dir $ACTION_DIR --bounded-action-id $BOUNDED_ACTION_ID <COMMAND...>', postrun)
        self.assertNotIn('REVIEW/RECOMMENDATION ONLY', postrun)
        self.assertNotIn('Do not execute follow-up QC/LEAN/CLI actions', postrun)

        self.assertNotIn('cleanup)', wrapper)
        self.assertIn('--bounded-action-id', wrapper)
        self.assertIn('bounded action id already used', wrapper)
        self.assertIn('bounded action id expired', wrapper)
        self.assertIn('bounded action id output context mismatch', wrapper)
        self.assertIn('bounded action id runner is not active', wrapper)
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


if __name__ == '__main__':
    unittest.main()
