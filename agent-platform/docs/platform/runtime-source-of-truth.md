# Runtime source of truth

Production runtime scripts and systemd units that make the Trader agents run must be represented in this repository before they are deployed to the VPS.

## Rule

Do not create long-lived runtime scripts or systemd units only by heredoc inside the deploy workflow or by manual edits on the server. Add them under `agent-platform/runtime/` and have the deploy workflow install those files.

Current runtime-owned locations:

- `agent-platform/runtime/bin/` -> `/usr/local/bin/`
- `agent-platform/runtime/systemd/` -> `/etc/systemd/system/`

The deploy workflow may still create short-lived temp files and server-local secret/config placeholders, but durable executable behavior and service schedules should be versioned here.

## Why this matters

The live VPS must not become the only copy of behavior. If a helper script, timer, or service is edited only on the host, PR review and `review-agent/pass` cannot see it, and agents cannot reliably compare intended state with deployed state.

## Cross-repo channel caveat

The external reviewer / Trader message bridge uses the separate repository `atzmonpersonalassistant/agent-message-site`. That repo is not governed by this repository's branch protection. It should have its own branch protection/ruleset before it is treated as a controlled operational channel.
