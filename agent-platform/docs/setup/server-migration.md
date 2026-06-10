# Server Migration / New VPS Setup

Goal: move the agent platform to a new VPS by changing GitHub deploy secrets and installing runtime secrets on the new server.

## What changing GitHub secrets covers

Updating these GitHub Actions secrets points deploys at the new server:

- `VPS_HOST`
- `VPS_USER`
- `VPS_SSH_PRIVATE_KEY`
- `VPS_SSH_HOST_KEY`

The deploy workflow also installs the shared QuantConnect env file from these GitHub Secrets:

- `QUANTCONNECT_USER_ID`
- `QUANTCONNECT_API_TOKEN`

This covers GitHub Actions SSH deploy plus QuantConnect credential installation. It does not copy GitHub App private keys or Codex/OpenAI auth.

## What must exist on the new server

The new server also needs the bootstrap script applied first:

```bash
sudo agent-platform/scripts/bootstrap-new-vps.sh
# or, on a minimal Ubuntu server:
sudo agent-platform/scripts/bootstrap-new-vps.sh --install-system-packages
```

The script creates users, directories, permissions, sudoers rules, and placeholder config paths. It deliberately does **not** install secrets.

After bootstrap, the server needs:

1. Linux users:
   - `agent-orchestrator`
   - `agent-coding`
   - `agent-review`
   - optional future: `agent-validator`
   - `agent-research`

2. Directory layout:
   - `/agents/orchestrator/{state,logs,backups}`
   - `/agents/coding/{workspaces,logs}`
   - `/agents/review/{workspaces,logs}`
   - `/agents/research/{state,logs,reports}` owned by `agent-research`
   - `/etc/trading-agents/secrets/{orchestrator,coding,review,validator,research}`
   - `/etc/trading-agents/secrets/quantconnect/env`, installed by `vps-deploy.yml` from GitHub Secrets and readable only by `root` plus the `agent-quantconnect` group. Current members are limited to non-prompt-driven QuantConnect runner roles (`agent-orchestrator`, `agent-validator`, and `agent-research`); prompt-driven coding/review users should not receive raw token access.

3. GitHub App private keys:
   - `/etc/trading-agents/secrets/orchestrator/private-key.pem`
   - `/etc/trading-agents/secrets/coding/private-key.pem`
   - `/etc/trading-agents/secrets/review/private-key.pem`
   - optional: `/etc/trading-agents/secrets/validator/private-key.pem`
   - optional/future: `/etc/trading-agents/secrets/research/private-key.pem`

4. Agent config files:
   - `/agents/coding/config.json`
   - `/agents/review/config.json`
   - orchestrator defaults or config as needed

5. Codex/OpenAI auth for the users that run Codex:
   - `/home/agent-coding/.codex/auth.json`
   - `/home/agent-review/.codex/auth.json`
   - future, if the research agent uses Codex directly: `/home/agent-research/.codex/auth.json`

6. Systemd units/timers for orchestrator dispatch/review flow. Basic sudoers dispatch rules are created by `agent-platform/scripts/bootstrap-new-vps.sh`.

## Private keys: copy vs regenerate

Two valid options:

### Option A — copy existing GitHub App private keys

Securely copy the existing `.pem` files from the old VPS to the same paths on the new VPS and preserve ownership/mode.

Pros: fastest.

Cons: old and new servers both have working keys until old secrets are removed.

### Option B — generate new GitHub App private keys

Generate a new private key for each GitHub App in GitHub settings, install it on the new VPS, then delete/revoke old keys after validation.

Pros: cleaner security posture.

Cons: more manual setup.

Recommendation: use Option B for a permanent migration; Option A is acceptable for a temporary test migration if the old VPS remains trusted.

## Codex/OpenAI auth

Codex auth is local to each Linux user. On a new VPS either:

- run Codex login/auth as `agent-coding` and `agent-review`, or
- install a managed API-key based auth file/environment in those users' homes.

Do not store Codex auth in GitHub unless deliberately switching to GitHub Actions-hosted model execution. The current design keeps model credentials on the VPS.

## Validation checklist

After migration:

```bash
sudo -n -u agent-orchestrator trading-orchestrator status
sudo -n -u agent-orchestrator trading-orchestrator cleanup-workspaces --older-than-hours 24
sudo -n -u agent-review env HOME=/home/agent-review trading-review-agent review --pr <safe-test-pr>
sudo -n -u agent-coding trading-coding-agent run --issue <safe-test-issue> --skip-codex
```

Then trigger `vps-deploy.yml` from GitHub Actions and confirm it deploys successfully to the new server. The deploy verifies that `agent-orchestrator` and `agent-research` can source `/etc/trading-agents/secrets/quantconnect/env` and see non-empty QuantConnect variables without printing the secret values.

## GitHub App token helper config

The reusable token helper reads app IDs, installation IDs, and private-key paths from:

```text
/etc/trading-agents/github-apps.json
```

or from the path in `TRADING_AGENT_APPS_CONFIG`.

Use `agent-platform/config-examples/github-apps.example.json` as the template. The config file contains IDs and paths, not private-key contents, but it should still be treated as server-local operational config.

Each role entry may include `linux_user`. If omitted, the token helper expects `agent-<role>`; for example `coding` must run as `agent-coding`.

## Sudoers dispatch rule

The orchestrator should dispatch coding work only through root-owned validation wrappers. It should not get wildcard sudo access to the full `trading-coding-agent` CLI.

Example sudoers snippet at `/etc/sudoers.d/trading-agent-orchestrator-dispatch`:

```text
agent-orchestrator ALL=(root) NOPASSWD: /usr/local/sbin/trading-dispatch-coding-agent *
agent-orchestrator ALL=(root) NOPASSWD: /usr/local/sbin/trading-dispatch-coding-agent-stub *
```

Validate with:

```bash
sudo visudo -cf /etc/sudoers.d/trading-agent-orchestrator-dispatch
sudo -n -u agent-orchestrator sudo -n /usr/local/sbin/trading-dispatch-coding-agent run --issue 1
```
