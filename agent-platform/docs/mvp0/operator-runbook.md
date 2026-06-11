# MVP-0 Operator Runbook

## Manual commands

Run on the VM unless noted.

```bash
# Orchestrator state
sudo -n -u agent-orchestrator trading-orchestrator status
sudo -n -u agent-orchestrator trading-orchestrator scan
sudo -n -u agent-orchestrator trading-orchestrator claim
sudo -n -u agent-orchestrator trading-orchestrator scan-prs
sudo -n -u agent-orchestrator trading-orchestrator enable-auto-merge
sudo -n -u agent-orchestrator trading-orchestrator route-review-failures
sudo -n -u agent-orchestrator trading-orchestrator db backup
sudo -n -u agent-orchestrator trading-orchestrator outbox next

# Coding Agent
sudo -n -u agent-coding trading-coding-agent run --issue <number>
sudo -n -u agent-coding trading-coding-agent run --issue <number> --fix-pr <pr-number>

# Review Agent
sudo -n -u agent-review env HOME=/home/agent-review trading-review-agent review --pr <number>

# Scheduler
sudo systemctl status trading-orchestrator.timer --no-pager
sudo systemctl status trading-orchestrator.service --no-pager
sudo systemctl start trading-orchestrator.service
sudo journalctl -u trading-orchestrator.service -n 100 --no-pager
```

## Log locations

```text
/agents/orchestrator/logs/tick.log
/agents/coding/logs/coding-agent.jsonl
/agents/coding/logs/codex-issue-*.txt
/agents/review/logs/review-agent.jsonl
/agents/review/workspaces/pr-*/.review-agent/review.md
/agents/review/workspaces/pr-*/.review-agent/model-review.md
```

Failed worker artifacts are preserved in the per-issue/per-PR workspaces:

```text
/agents/coding/workspaces/issue-*/
/agents/review/workspaces/pr-*/
```

Lean/QuantConnect project files are split between role-private workspaces and shared platform directories:

```text
/agents/coding/lean-workspace
/agents/review/lean-workspace
/agents/research/lean-workspace
/agents/validator/lean-workspace
/agents/shared/lean-projects
/agents/shared/research-artifacts
```

These shared directories are collaborative Lean workspaces. Deploy configures them with `agent-lean` setgid permissions and default ACLs when `setfacl` is installed, then validates that one Lean-capable role can create a file and another can modify it. If ACL tooling is not available on a host, any wrapper that writes to these shared trees must set `umask 0002`.

`agent-coding` and `agent-review` may work with Lean files, but they must not have raw QuantConnect token access. Check that boundary without printing secrets:

```bash
sudo -n -u agent-coding test ! -r /etc/trading-agents/secrets/quantconnect/env
sudo -n -u agent-review test ! -r /etc/trading-agents/secrets/quantconnect/env
sudo -n -u agent-research test -r /etc/trading-agents/secrets/quantconnect/env
sudo -n -u agent-validator test -r /etc/trading-agents/secrets/quantconnect/env
```

## Human approval relay

Approval outbox payloads use this shape:

```json
{
  "type": "approval_request",
  "pr": 45,
  "title": "...",
  "reason": "...",
  "risk_summary": "...",
  "url": "https://github.com/.../pull/45",
  "allowed_replies": ["approve", "reject"]
}
```

Allowed replies:

```bash
sudo -n -u agent-orchestrator trading-orchestrator inbox ack --outbox-id approval-pr-45 --decision approve
sudo -n -u agent-orchestrator trading-orchestrator inbox ack --outbox-id approval-pr-45 --decision reject
```

Approve adds `human:approved` and comments `/human-approved`.
Reject adds `human:rejected` and comments `/human-rejected`.
