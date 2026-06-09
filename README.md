# Trader

Trading research, agent infrastructure, and options-system experiments.

## Current Structure

### `options-trade-lab/`

Main project area for options research, strategy design, scanner planning, validation, and future implementation.

- Main docs: `options-trade-lab/README.md`
- Architecture: `options-trade-lab/ARCHITECTURE.md`
- Project plan: `options-trade-lab/PROJECT_PLAN.md`
- Strategy/platform docs: `options-trade-lab/docs/`
- Context notes: `options-trade-lab/context/`
- Historical MVP-0/platform notes: `options-trade-lab/archive/`

Future scanner work should be implemented under this coherent project structure, not as separate top-level radar folders.

### `ibkr-client/`

Read-only Interactive Brokers connectivity utilities for **IB Gateway only**. Starts with local Paper Trading checks only: managed accounts, account summary, positions, and one quote snapshot.

- Main docs: `ibkr-client/README.md`
- Main script: `ibkr-client/client.py`
- Outputs: stdout by default, or `ibkr-client/output/client.json` when `--output` is supplied

## Removed Legacy Folders

The old standalone radar/planning folders were removed from the active repo layout:

- `options-radar/`
- `market-radar/`
- `earnings-volatility-radar/`
- top-level `plans/`

They should not be used as source-of-truth going forward.

## VPS access

<vps-provider> VPS used for simple always-on agent/trader infrastructure experiments:

```bash
# SSH with the dedicated key created on the assistant Mac
ssh -i <private-ssh-key-path> <vps-admin-user>@<vps-ip>

# Optional: add a local SSH alias
cat >> ~/.ssh/config <<'EOF'
Host trader-ovh
  HostName <vps-ip>
  User ubuntu
  IdentityFile <private-ssh-key-path>
EOF

# Then connect with:
ssh trader-ovh
```

Host details:

```text
host: vps-ce2ba5e7.vps.ovh.ca
ip: <vps-ip>
user: ubuntu
key: <private-ssh-key-path>
```

Do not commit passwords or private keys. The SSH private key stays local.

## Safety

These tools are for research and alerting only. Information only, not investment advice. Verify quotes, liquidity, bid/ask spreads, and risk manually before any trade.
