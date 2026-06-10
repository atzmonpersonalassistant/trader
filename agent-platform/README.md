# Agent Platform

Reusable agentic development platform extracted from this repo.

This module contains the architecture built so far:

- Orchestrator agent — polls GitHub issues/PRs, dispatches work, routes review failures, manages outbox notifications, and enables safe auto-merge.
- Coding agent — works on GitHub issues in isolated workspaces and opens/fixes PRs.
- Review agent — independently reviews PRs, publishes required checks, and can run an optional second-pass autoreview.
- GitHub App token helper — mints short-lived installation tokens from per-agent GitHub App private keys.
- MVP-0 docs/runbooks — historical but useful setup and operating notes.

## Current runtime inventory

As of the current VPS setup, the **implemented and deployed** agent CLIs are:

1. `trading-orchestrator` running as Linux user `agent-orchestrator`.
2. `trading-coding-agent` running as Linux user `agent-coding` when dispatched.
3. `trading-review-agent` running as Linux user `agent-review` when reviewing PRs.

This repo also includes a research-agent CLI:

4. `trading-research-agent` — implemented in `agent-platform/tools/` and included in the deploy workflow. It seeds/lists strategy hypothesis queues and exposes the default Lean-first / QC Cloud research prompt. The deploy workflow provisions a dedicated `agent-research` Linux user, owns `/agents/research/{state,logs,reports,lean-workspace}` with that user, gives it access to the shared QuantConnect env through the `agent-quantconnect` group, and logs Lean CLI into QuantConnect without printing secrets. It is not yet wired into an orchestrator timer.

The VPS also has an `agent-validator` Linux user, but there is not yet a deployed `trading-validator-agent` CLI. Treat this as a placeholder for a future Quant Research Validator Agent. `agent-validator` also has QuantConnect env access for future independent validation.

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

See `docs/security-and-secrets.md`, `docs/setup/server-migration.md`, and `docs/platform/research-agent-qc-workflow.md` before moving to a new server or sharing this module.
