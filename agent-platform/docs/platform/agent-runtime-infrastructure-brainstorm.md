# Agent Runtime Infrastructure Brainstorm

Status: planning notes  
Project: `atzmonpersonalassistant/trader`  
Goal: continuously improve the QuantConnect options research/trading platform with autonomous agents, while keeping review/governance separated from code writing.

---

## 1. Core Question

We want a system where agents can work continuously on the `trader` repo, open PRs, review PRs, validate quant research/backtests, and report results.

The key design concern is whether the same agent/runtime should both write code and review/approve it. The current conclusion is: **no**. Code writing and governance should be separated.

---

## 2. Logical Agents

The system should keep five logical agent roles:

1. **Coding Agent**
   - Writes code.
   - Works on GitHub issues.
   - Opens branches and PRs.
   - Fixes CI/review comments.
   - Does **not** choose trading strategies.

2. **Review Agent**
   - Reviews PR diffs.
   - Checks code quality, tests, secrets, and implementation safety.
   - Performs a quant-specific PR checklist where relevant.
   - Should be independent from the Coding Agent session.

3. **Strategy / Quant Research Agent**
   - Generates strategy hypotheses and experiment queues.
   - Defines entry/exit rules, data requirements, risk caps, and discard criteria.
   - Reads QuantConnect reports and decides whether to discard, refine, or retest a hypothesis.
   - Does **not** write production code, approve PRs, or place trades.
   - First target family: cheap upside via long calls, low-debit bull call spreads, calendars/diagonals, and LEAPS call spreads.
   - Current status: tested as an ad-hoc OpenClaw sub-agent; not yet implemented as a persistent `trading-research-agent` CLI.

4. **Quant Research Validator Agent**
   - Reviews backtest/sweep results as an independent governance role.
   - Looks for overfitting, weak baselines, bad risk assumptions, and unstable performance.
   - Decides whether research is ready for paper promotion.
   - Can mark issues as `agent:ready` when evidence is sufficient.
   - Current status: `agent-validator` Linux user exists on the VPS, but no deployed validator CLI exists yet.

5. **Reporting / Orchestration Agent**
   - Creates follow-up issues.
   - Updates experiment registry.
   - Sends WhatsApp summaries.
   - Opens promotion PRs when validation passes.

These are separate **roles**, even if some share the same physical machine or subscription later.

---

## 3. Preferred Physical Architecture

Uriel prefers splitting machines from the start.

### VM 1: Builder

Name suggestion: `trader-builder`

Purpose:

- Run the Coding Agent.
- Use Codex as the main coding model.
- Work from the GitHub backlog.
- Open PRs, but not approve itself.

Model:

- Codex

GitHub identity:

- Dedicated coding identity, e.g. `trader-coding-agent`.

Permissions:

- Read repo/issues/actions.
- Create branches.
- Push branches.
- Open PRs.
- Comment on own PRs.
- No direct push to `main`.
- No branch protection/admin permissions.
- No live-trading secrets.

### VM 2: Governance

Name suggestion: `trader-governance`

Purpose:

- Run the Review Agent.
- Run the Quant Research Validator Agent.
- Run the Reporting/Orchestration Agent.
- Act as the independent governance and reporting layer.

Models:

- Review Agent: Codex
- Quant Validator: Claude
- Reporter/Orchestrator: Claude

GitHub identity:

- Dedicated review/governance identity, e.g. `trader-review-agent`, or a GitHub App.

Permissions:

- Read repo/issues/actions/artifacts.
- Write PR reviews/comments/check statuses.
- Create/update issues.
- Trigger/observe workflows.
- Send WhatsApp summaries through the configured notification path.
- No direct implementation commits to the Coding Agent branches by default.
- No direct merge to `main` unless explicitly allowed later.

---

## 4. Communication Model

The agents do **not** need to talk to each other directly.

Preferred communication layer:

```text
GitHub issues / PRs / checks / comments / labels / artifacts
```

Flow:

```text
Issue marked agent:ready
  -> Coding Agent picks it up
  -> Coding Agent opens branch + PR
  -> Governance VM sees PR
  -> Review Agent reviews diff and posts check/comments
  -> Quant Validator runs required validation where relevant
  -> Coding Agent responds to comments/failing checks
  -> Reporting Agent summarizes important events
```

GitHub acts as the message bus and audit trail.

Advantages:

- No hidden agent-to-agent conversations.
- Every decision is attached to an issue, PR, check, or artifact.
- Easy to pause work with labels or branch protection.
- Human-readable audit trail.
- Cleaner failure recovery.

---

## 5. Runtime Question: OpenClaw vs Claude/Codex CLI vs Hermes

The models alone are not enough. Claude/Codex are the “brain”; the system still needs runtime/orchestration.

A runtime must handle:

- polling/scheduling/event handling
- issue selection
- state persistence
- logs
- retries
- cost/budget limits
- tests and shell commands
- GitHub PR/check/comment operations
- crash recovery
- watchdog behavior
- notification/reporting

### Option A: OpenClaw on the VMs

Pros:

- Already has tools, sessions, cron, memory, WhatsApp/reporting paths, and agent orchestration patterns.
- Good fit for a personal autonomous system.
- Can route different jobs to different models.

Cons:

- Needs to be configured as a stable cloud daemon.
- Needs careful permission and secret isolation.

### Option B: Hermes / custom orchestrator

Potentially good if it supports:

- GitHub integration
- background workers
- agent/job scheduling
- state and logs
- secrets isolation
- multi-model routing
- budget limits
- notification hooks

Needs evaluation before choosing.

### Option C: Keep Claude/Codex open in tmux

Pros:

- Very simple to start.

Cons:

- Brittle.
- Poor lifecycle management.
- Weak cost control.
- Weak crash recovery.
- Harder to audit.
- Not production-like.

Current conclusion: **do not rely on “open Claude and let it run” as the final design**. Use an event-loop/runtime that invokes agents for bounded jobs.

---

## 6. Model Routing

Proposed routing:

| Role | Preferred model |
|---|---|
| Coding Agent | Codex |
| Review Agent | Codex |
| Quant Validator | Claude |
| Reporting/Orchestration | Claude |

Rationale:

- Codex is strong for code changes, tests, diffs, and implementation review.
- Claude is strong for synthesis, risk reasoning, research validation, reporting, and skeptical analysis.

---

## 7. Reviewer Context

The Review Agent should not receive the Coding Agent's full internal transcript or reasoning.

It should receive:

- PR diff
- PR title/body
- linked issue and acceptance criteria
- relevant specs/plans
- changed files and nearby context
- CI/test/lint/notebook results
- guardrail checklist

It should not receive:

- Coding Agent private transcript
- secrets
- irrelevant memory
- unnecessary full machine context

The reviewer should behave like a cold, independent judge of the PR.

### Review Idempotency

The Review Agent must not write repeated reviews for the same code state.

A PR review should be keyed by at least:

```text
repo
pr_number
head_sha
review_agent_version
review_policy_version
relevant_context_hash
```

Before writing a new review/check/comment, the Review Agent should check whether it has already reviewed the current `head_sha` with the same policy/context. If yes, it should not post another duplicate review.

Allowed reasons to review again:

- PR head SHA changed.
- Review policy/checklist changed.
- Relevant plan/spec file changed.
- CI/test/backtest result changed materially.
- Human explicitly requested re-review with a command/label/comment.
- Prior review failed/incomplete due to tool/runtime error.

Preferred output behavior:

- Use GitHub Check Runs as the canonical pass/fail state for the current SHA.
- Post a PR comment only when there are new findings or a meaningful status change.
- If the same finding still applies, update/replace the prior bot comment if practical, or avoid reposting noise.

### PR Readiness Trigger

It may be better for the heavier Claude-based Validator to wake only after the PR reaches a useful state, rather than every polling cycle.

Potential readiness conditions:

```text
PR is open
PR is not draft
head_sha has not been validated yet
required CI finished
unit/lint/notebook checks passed or produced artifacts
backtest smoke/full results are available when relevant
```

Recommended behavior:

- Codex Review Agent can run early on diff/static checks.
- Claude Quant Validator should usually wait until CI/backtest artifacts exist, or until the PR is explicitly marked ready for validation.
- Reporter should summarize only meaningful transitions, not every polling cycle.

This reduces duplicate comments, wasted model calls, and noisy reviews.

Expected output:

```text
PASS / BLOCK
Concrete findings
Required fixes if blocked
Risk notes if relevant
```

---

## 8. Governance and Identity

It is not ideal for the same GitHub identity to both write code and approve/review it.

Preferred long-term setup:

- Coding identity: `trader-coding-agent`
- Governance/review identity: `trader-review-agent` or GitHub App

MVP can technically start with one identity and separate checks, but Uriel prefers real separation if practical.

Branch protection should require Governance checks before merge:

- tests
- lint
- required notebook checks
- `review-agent`
- `quant-validator`

---

## 9. Access and Secrets

The agents need broad operational access, but not identical permissions.

Principle:

```text
Broad environment visibility, scoped write permissions, and secrets only where operationally required.
```

Guidelines:

- Builder can write branches and PRs, but cannot approve/merge itself.
- Governance can write checks/comments/issues, but does not implement code by default.
- QuantConnect research/paper secrets should be available only to workflows/runners that need them.
- Live secrets should not exist in the MVP.
- Secrets should not be exposed directly to model context.

---

## 10. Cost Components to Track

Likely monthly costs:

- Existing Codex/OpenClaw subscription: about ₪300/month.
- Possible second Codex/subscription later: about ₪300/month if needed.
- Google Cloud VMs:
  - `e2-medium`: roughly ₪90–130/month.
  - `e2-standard-2`: roughly ₪185–260/month plus disk.
  - Two `e2-standard-2` VMs: roughly ₪370–520/month plus disks.
- QuantConnect:
  - free tier may be enough only for small experiments.
  - paid research tier roughly $20/month and up, depending on compute/live needs.
- Claude:
  - Pro/Max/API depending on automation requirements.
- Optional review tooling:
  - CodeRabbit Pro roughly $24–30/month if adopted later.
  - Baz/Bazz pricing unclear / likely not required for MVP.

Recommended initial budget target:

```text
Two GCP VMs + existing Codex + basic QuantConnect + Claude budget cap.
```

Avoid adding CodeRabbit/Baz/second Codex subscription until the agent loop proves useful.

---

## 11. Current Preferred Direction

Start with:

```text
VM 1: trader-builder
  - Coding Agent
  - Codex
  - dedicated coding GitHub identity

VM 2: trader-governance
  - Review Agent using Codex
  - Quant Validator using Claude
  - Reporter/Orchestrator using Claude
  - dedicated governance GitHub identity/App

Communication:
  - GitHub only
  - issues, PRs, comments, checks, artifacts, labels

Runtime:
  - OpenClaw, Hermes, or custom event-loop still to be selected
  - Do not use an unmanaged long-running Claude/Codex chat as the final architecture
```


---

## 12. Agent Health / Heartbeat Monitor

Add a lightweight health-monitor agent/process whose only job is to reflect the operational status of all agents to Uriel.

Logical name:

```text
Agent Health Monitor
```

This can run on the Governance VM. It does not need its own model most of the time; a script is enough. Claude can be invoked only when summarization or anomaly explanation is useful.

Responsibilities:

- Track whether each agent is alive and running on schedule.
- Track last successful cycle per agent.
- Track last attempted task per agent.
- Track current status: idle, working, blocked, failed, degraded.
- Track GitHub API/auth health.
- Track model backend health: Codex available, Claude available.
- Track budget/cost limits if available.
- Track VM disk/CPU/memory basics.
- Track stuck jobs and repeated failures.
- Send concise heartbeat summaries to Uriel.

Suggested monitored agents:

```text
trader-builder / Coding Agent
trader-governance / Review Agent
trader-governance / Quant Validator
trader-governance / Reporter-Orchestrator
```

Suggested state file/table fields:

```text
agent_id
role
host
last_cycle_started_at
last_cycle_finished_at
last_success_at
last_error_at
last_error_summary
current_state
current_task_ref
last_github_object
model_backend
model_last_ok_at
consecutive_failures
```

Suggested heartbeat cadence:

- Internal health check: every 5–10 minutes.
- User-facing summary: once or twice per day if everything is healthy.
- Immediate alert: critical failure, auth failure, budget cap hit, repeated failures, stuck job, disk full, or no successful cycle for too long.

Example normal report:

```text
Trader agents heartbeat:
- Builder: healthy, idle, last cycle 09:40
- Reviewer: healthy, reviewed PR #12 at 09:35
- Quant Validator: healthy, no pending artifacts
- Reporter: healthy, last summary sent yesterday 22:10
- Issues: none
```

Example alert:

```text
Trader agents alert:
- Reviewer failed 3 consecutive cycles.
- Cause: GitHub token expired / 401.
- Impact: PR reviews are not running.
- Suggested action: rotate trader-review-agent token.
```

The Health Monitor should not become the primary orchestrator. It observes and reports. The individual agents still decide their own work by polling GitHub.

---

## 13. Open Questions

1. Should the runtime be OpenClaw, Hermes, or a small custom daemon?
2. Should the two GitHub identities be machine users or GitHub Apps?
3. Can Codex/Claude subscriptions be used safely for daemonized automation, or is API billing required?
4. What hard monthly budget cap should be enforced for each model/backend?
5. Should Governance ever be allowed to auto-merge, or only approve/check while GitHub auto-merge completes?
6. Should Builder be allowed to run QuantConnect jobs, or should only Governance/CI run them?
7. What is the minimal first autonomous workflow to prove value?

---

## 14. Suggested Next Step

Before provisioning cloud infrastructure, define a concrete MVP runtime plan:

1. Pick runtime: OpenClaw vs Hermes vs custom daemon.
2. Pick GitHub identity strategy: machine users vs GitHub Apps.
3. Define exact permissions for Builder and Governance.
4. Define first autonomous workflow:
   - issue with `agent:ready`
   - Builder opens PR
   - Governance reviews and validates
   - Reporter sends summary
5. Set budget caps and watchdog behavior.
