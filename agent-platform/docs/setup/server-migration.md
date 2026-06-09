# Server Migration / New VPS Setup

Goal: move the agent platform to a new VPS by changing GitHub deploy secrets and installing runtime secrets on the new server.

## What changing GitHub secrets covers

Updating these GitHub Actions secrets points deploys at the new server:

- `VPS_HOST`
- `VPS_USER`
- `VPS_SSH_PRIVATE_KEY`
- `VPS_SSH_HOST_KEY`

This only covers GitHub Actions SSH deploy.

## What must exist on the new server

The new server also needs:

1. Linux users:
   - `agent-orchestrator`
   - `agent-coding`
   - `agent-review`
   - optional future: `agent-validator`

2. Directory layout:
   - `/agents/orchestrator/{state,logs,backups}`
   - `/agents/coding/{workspaces,logs}`
   - `/agents/review/{workspaces,logs}`
   - `/etc/trading-agents/secrets/{orchestrator,coding,review,validator}`

3. GitHub App private keys:
   - `/etc/trading-agents/secrets/orchestrator/private-key.pem`
   - `/etc/trading-agents/secrets/coding/private-key.pem`
   - `/etc/trading-agents/secrets/review/private-key.pem`
   - optional: `/etc/trading-agents/secrets/validator/private-key.pem`

4. Agent config files:
   - `/agents/coding/config.json`
   - `/agents/review/config.json`
   - orchestrator defaults or config as needed

5. Codex/OpenAI auth for the users that run Codex:
   - `/home/agent-coding/.codex/auth.json`
   - `/home/agent-review/.codex/auth.json`

6. Systemd units/timers and sudoers rules for orchestrator dispatch/review flow.

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

Then trigger `vps-deploy.yml` from GitHub Actions and confirm it deploys successfully to the new server.
