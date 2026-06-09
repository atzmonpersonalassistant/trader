# Security and Secrets

This agent platform is reusable, but the running VPS contains real secrets. Do not clone or share the VPS as-is.

## Secrets on GitHub

GitHub Actions uses repository secrets for deploying to the VPS:

- `VPS_HOST` — target server host/IP.
- `VPS_USER` — SSH user used by the deploy workflow.
- `VPS_SSH_PRIVATE_KEY` — private key GitHub Actions uses to SSH to the VPS.
- `VPS_SSH_HOST_KEY` — pinned SSH host key for strict host-key checking.

These are stored under the repo's GitHub Actions secrets. GitHub does not let us read the values back; we can only create, update, or delete them.

If the server changes, update these secrets. That is enough for deploy SSH, but not enough to make the agents functional unless the new server also has Codex auth and GitHub App keys installed.

## Secrets on the VPS

Current sensitive runtime locations:

### Codex/OpenAI auth

- `/home/agent-coding/.codex/auth.json`
- `/home/agent-review/.codex/auth.json`

These include `OPENAI_API_KEY` and Codex access/refresh tokens. They are mode `600` and owned by the corresponding Linux user.

### GitHub App private keys

- `/etc/trading-agents/secrets/orchestrator/private-key.pem`
- `/etc/trading-agents/secrets/coding/private-key.pem`
- `/etc/trading-agents/secrets/review/private-key.pem`
- `/etc/trading-agents/secrets/validator/private-key.pem`

These allow the token helper to mint short-lived GitHub installation tokens for each GitHub App.

### Runtime state and logs

- `/agents/orchestrator/state/orchestrator.db`
- `/agents/*/logs/`
- `/agents/*/workspaces/`

These are not necessarily secrets, but they can contain repo context, issue text, review outputs, and operational history. Do not share them casually.

## Principle

The repo should contain only architecture, code, docs, and non-secret examples.

Every server must be provisioned with its own secrets. For a server migration, either securely copy secrets from the old VPS or regenerate/re-auth them on the new one.

## Token helper config

`trading-agent-token` should read role-to-App mapping from server-local config, normally:

```text
/etc/trading-agents/github-apps.json
```

The repo includes only `agent-platform/config-examples/github-apps.example.json` with placeholder IDs. Do not hard-code real App IDs or private-key paths that are specific to a private deployment into reusable docs/code unless they are intentionally public examples.

The token helper also enforces the Linux user boundary: by default role `coding` may only be minted by OS user `agent-coding`, `review` by `agent-review`, and so on. Override with `linux_user` in `/etc/trading-agents/github-apps.json` only if the server uses different account names.
