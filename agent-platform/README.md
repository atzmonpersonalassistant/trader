# Agent Platform

Reusable agentic development platform extracted from this repo.

This module contains the architecture built so far:

- Orchestrator agent — polls GitHub issues/PRs, dispatches work, routes review failures, manages outbox notifications, and enables safe auto-merge.
- Coding agent — works on GitHub issues in isolated workspaces and opens/fixes PRs.
- Review agent — independently reviews PRs, publishes required checks, and can run an optional second-pass autoreview.
- GitHub App token helper — mints short-lived installation tokens from per-agent GitHub App private keys.
- MVP-0 docs/runbooks — historical but useful setup and operating notes.

The goal is that someone can copy `agent-platform/` and understand/adapt the architecture without copying the options trading project.

## What is reusable

```text
agent-platform/
  tools/              CLI tools and agent implementations
  tests/              unit tests for orchestrator/coding/review behavior
  docs/               runbooks, setup notes, migration/security docs
  config-examples/    non-secret example configs
```

GitHub Actions workflows must remain under `.github/workflows/`, but `vps-deploy.yml` deploys files from `agent-platform/tools/`.

## What is not reusable / not included

Secrets and machine-local runtime state are intentionally excluded:

- Codex/OpenAI auth files
- GitHub App private keys
- VPS SSH keys
- `/agents/*/state`, logs, and workspaces
- GitHub Actions secret values

See `docs/security-and-secrets.md` and `docs/setup/server-migration.md` before moving to a new server or sharing this module.
