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
