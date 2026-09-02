# Google Sheet message bridge

This bridge closes the external reviewer intake gap:

```text
Claude/external reviewer -> agent-message-site -> Google Apps Script -> Google Sheet -> trading-message-bridge -> GitHub -> trading-orchestrator
```

## Components

- `atzmonpersonalassistant/agent-message-site`
  - `index.html`: public static page where the external reviewer submits a message.
  - `apps-script/Code.gs`: Google Apps Script receiver/read API.
  - Google Sheet: `1_LqP10O1unoRs7Jw9OYRoCtI3E6LKL2zFfiRfWh_H5I`.
- `atzmonpersonalassistant/trader`
  - `agent-platform/scripts/trading-message-bridge`: poller that reads new Sheet rows and routes them into GitHub.

## Routing behavior

For every new `message_log` row after the stored `last_row`:

1. If the message contains a GitHub PR/issue URL or `PR #123` / `issue #123`, the bridge posts a comment to that GitHub issue/PR and adds:
   - `agent:needs-fix`
   - `external:reviewer`
2. If no target is found, the bridge creates a new GitHub issue with label:
   - `external:reviewer`

Untargeted reviewer messages intentionally do not get `agent:ready` by default.
A human or later intake policy must opt them into coding dispatch after deciding that
the message is an actionable implementation request rather than review prose,
hypothesis, or context.

The local state file stores the last processed Sheet row, so rows are not replayed.

## Required configuration

Apps Script must be deployed with script property:

- `BRIDGE_TOKEN`: random shared secret used only by the bridge read API.

The VPS/runtime must provide:

- `TRADING_MESSAGE_BRIDGE_URL`: deployed Apps Script web app URL.
- `TRADING_MESSAGE_BRIDGE_TOKEN`: same secret as Apps Script `BRIDGE_TOKEN`.
- optional `TRADING_MESSAGE_BRIDGE_STATE`: defaults to `/agents/orchestrator/state/message-bridge-state.json`.

## First run

To avoid replaying old historical Sheet rows:

```bash
trading-message-bridge --start-at-latest
```

Then subsequent runs can poll normally. The bridge calls the Apps Script read API with POST JSON so the shared token is not placed in URL query strings:

```bash
trading-message-bridge
```

Use `--dry-run` before enabling real GitHub writes.
