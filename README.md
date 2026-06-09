# Trader

Trading research, agent infrastructure, and options-system experiments.

## Current Structure

### `options-trade-lab/`

Research-first options trading lab for strategy design, scanner planning, validation, and future implementation.

- Main docs: `options-trade-lab/README.md`
- Architecture: `options-trade-lab/ARCHITECTURE.md`
- Project plan: `options-trade-lab/PROJECT_PLAN.md`
- Strategy/platform docs: `options-trade-lab/docs/`
- Context notes: `options-trade-lab/context/`

Future scanner work should be implemented under this coherent project structure, not as separate top-level radar folders.

### `plans/`

Platform and infrastructure planning documents.

- `plans/mvp0/` — MVP-0 agentic development loop setup, runbook, costs, and task breakdown.
- `plans/platform/` — broader agent runtime/platform architecture notes.

### `ibkr-client/`

Read-only Interactive Brokers connectivity utilities for **IB Gateway only**. Starts with local Paper Trading checks only: managed accounts, account summary, positions, and one quote snapshot.

- Main docs: `ibkr-client/README.md`
- Main script: `ibkr-client/client.py`
- Outputs: stdout by default, or `ibkr-client/output/client.json` when `--output` is supplied

## Removed Legacy Folders

The old standalone radar folders were removed from the active repo layout:

- `options-radar/`
- `market-radar/`
- `earnings-volatility-radar/`

They should not be used as source-of-truth going forward.

## VPS access

OVHcloud VPS used for simple always-on agent/trader infrastructure experiments:

```bash
# SSH with the dedicated key created on the assistant Mac
ssh -i ~/.ssh/ovh_vps_ce2ba5e7 ubuntu@144.217.82.149

# Optional: add a local SSH alias
cat >> ~/.ssh/config <<'EOF'
Host trader-ovh
  HostName 144.217.82.149
  User ubuntu
  IdentityFile ~/.ssh/ovh_vps_ce2ba5e7
EOF

# Then connect with:
ssh trader-ovh
```

Host details:

```text
host: vps-ce2ba5e7.vps.ovh.ca
ip: 144.217.82.149
user: ubuntu
key: ~/.ssh/ovh_vps_ce2ba5e7
```

Do not commit passwords or private keys. The SSH private key stays local.

## Safety

These tools are for research and alerting only. Information only, not investment advice. Verify quotes, liquidity, bid/ask spreads, and risk manually before any trade.
