from pathlib import Path
import unittest


class VpsDeployWorkflowTests(unittest.TestCase):

    def test_earnings_research_has_single_public_cli(self):
        workflow = Path('.github/workflows/vps-deploy.yml').read_text()

        self.assertIn('/agents/research/bin/earnings-qc-research', workflow)
        self.assertIn('/agents/research/libexec/earnings-qc-options/earnings-qc-options-scan', workflow)
        self.assertIn('/agents/research/libexec/earnings-qc-options/earnings-qc-multiyear-backtest', workflow)
        self.assertIn('rm -f /agents/research/bin/earnings-qc-options-full-scan', workflow)
        self.assertIn('test ! -e /agents/research/bin/earnings-qc-options-full-scan', workflow)

    def test_research_postgres_cache_db_is_provisioned(self):
        workflow = Path('.github/workflows/vps-deploy.yml').read_text()

        self.assertIn('postgresql postgresql-client', workflow)
        self.assertIn('systemctl enable --now postgresql', workflow)
        self.assertIn('CREATE ROLE "agent-research" LOGIN', workflow)
        self.assertIn('createdb -O "agent-research" trader_research', workflow)
        self.assertIn('CREATE SCHEMA IF NOT EXISTS earnings_cache AUTHORIZATION "agent-research"', workflow)
        self.assertIn('ALTER DATABASE trader_research SET search_path TO earnings_cache, public', workflow)
        self.assertIn('SELECT 1 AS research_postgres_ready', workflow)


if __name__ == '__main__':
    unittest.main()
