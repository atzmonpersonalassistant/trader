# Trader

Trading research, agent infrastructure, and options-system experiments.

## Current Structure

### `agent-platform/`

Reusable agentic development platform extracted from this repo.

- Agent tools: `agent-platform/tools/`
- Tests: `agent-platform/tests/`
- Docs/runbooks/setup: `agent-platform/docs/`
- Non-secret config examples: `agent-platform/config-examples/`

This is the part to copy or share if someone wants inspiration from the agent architecture.

### `planning/`

Main project area for options research, strategy design, scanner planning, validation, and future implementation.

- Main docs: `planning/README.md`
- Architecture: `planning/ARCHITECTURE.md`
- Project plan: `planning/PROJECT_PLAN.md`
- Strategy/platform docs: `planning/docs/`
- Context notes: `planning/context/`

Future scanner work should be implemented under this coherent project structure, not as separate top-level radar folders.

### `ibkr-client/`

Read-only Interactive Brokers connectivity utilities for **IB Gateway only**. Starts with local Paper Trading checks only: managed accounts, account summary, positions, and one quote snapshot.

- Main docs: `ibkr-client/README.md`
- Main script: `ibkr-client/client.py`
- Outputs: stdout by default, or `ibkr-client/output/client.json` when `--output` is supplied

## Removed Legacy Folders

Old standalone radar/planning folders were removed from the active repo layout. Future scanner work should live under `agent-platform/` or `planning/`, not as separate top-level radar folders.

## Secrets and VPS Runtime

Do not commit or share runtime secrets. The repo contains code/docs/examples only.

Current deploys use `.github/workflows/vps-deploy.yml`, with target server details stored as GitHub Actions secrets. See:

- `agent-platform/docs/security-and-secrets.md`
- `agent-platform/docs/setup/server-migration.md`

## Safety

These tools are for research and alerting only. Information only, not investment advice. Verify quotes, liquidity, bid/ask spreads, and risk manually before any trade.
