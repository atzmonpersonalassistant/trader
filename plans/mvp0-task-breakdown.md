# MVP-0 Task Breakdown — Agentic Dev Loop

Status: Draft
Owner: Uriel
Scope: MVP-0 only

---

## 1. MVP-0 Goal

Prove the agentic development loop on a real GitHub repo without QuantConnect and without a Quant Validator.

Target flow:

```text
GitHub issue with agent:ready
  -> Orchestrator polling detects it
  -> Coding Agent creates isolated workspace/worktree
  -> Coding Agent changes code/docs/tests
  -> Coding Agent opens PR
  -> Orchestrator detects PR
  -> Orchestrator enables GitHub native auto-merge
  -> Review Agent runs as a required check
  -> if review fails: Orchestrator routes back to Coding Agent
  -> if review passes and branch protection passes: GitHub squash-merges PR
```

Out of scope for MVP-0:

- Quant Validator
- QuantConnect backtests/sweeps
- paper trading
- live trading
- broker/IBKR integration
- OpenClaw runtime on the VM
- HTTP/webhook interface to the Orchestrator

---

## 2. Fixed Decisions for MVP-0

- Trading VM does not run or depend on OpenClaw.
- OpenClaw is an external WhatsApp/control relay only.
- Orchestrator uses polling only, every 10 minutes.
- OpenClaw talks to the Orchestrator through CLI on the VM.
- GitHub identities are GitHub Apps, not GitHub users.
- VM/process isolation uses separate Linux users.
- Primary secrets store is GCP Secret Manager; fallback is locked-down VM files only if billing/setup blocks progress.
- Orchestrator state is SQLite with `.backup`-based backups.
- Every PR is enrolled in GitHub native auto-merge by default.
- Merge method is squash merge.
- Orchestrator enables auto-merge, not the Coding Agent.
- Review Agent is a required check for every PR.
- Review failure routes automatically back to Coding Agent.
- Max review-fix retries: 50.
- No early-stop retry heuristics before the 50 cap, except mandatory human-approval gates.
- Human approval through WhatsApp is recorded in GitHub with both label and comment.
- GitHub state is the source of truth.

Mandatory human approval gates:

```text
- live trading changes
- IBKR/broker integration
- secrets/auth changes
- risk limits / position sizing caps
- first paper-trading promotion
- changes that weaken validation gates
- changes that remove or weaken slippage/cost/check requirements
- large dependency or security-sensitive changes
```

---

## 3. Task Groups

### Group A — Repository and Branch Protection

Status: Completed ✅

Completed evidence:

```text
Repo: atzmonpersonalassistant/trader
Default branch: main
Labels: created
Branch protection: enabled on main
Required status check: review-agent/pass
GitHub native auto-merge: enabled
Merge method: squash
Merge commits: disabled
Rebase merge: disabled
Delete branch on merge: enabled
Force push/deletion on main: disabled
```


#### A1. Confirm target repo

Goal: Confirm MVP-0 target repository.

Acceptance criteria:

- Repo owner/name is recorded in config.
- Repo exists and is accessible by Uriel.
- Default branch is identified, expected `main`.

Suggested output:

```yaml
github:
  owner: atzmonpersonalassistant
  repo: trader
  default_branch: main
```

---

#### A2. Define required branch protection checks

Goal: Decide the exact required checks for MVP-0.

Acceptance criteria:

- Required checks list exists.
- Includes Review Agent check.
- Does not include Quant Validator.
- Allows GitHub native auto-merge.
- Uses squash merge.

Initial required checks:

```text
- ci/tests or equivalent minimal CI
- review-agent/pass
```

---

#### A3. Configure squash merge as the preferred merge method

Goal: Ensure PRs merge as one commit.

Acceptance criteria:

- Squash merge is enabled for the repo.
- Merge commits and rebase merge are disabled if desired.
- Auto-merge is supported.

---

#### A4. Create MVP-0 GitHub labels

Goal: Create the labels needed for the first state machine.

Acceptance criteria:

Labels exist:

```text
agent:ready
agent:claimed
agent:in-progress
agent:pr-opened
agent:needs-fix
agent:blocked
needs:human-approval
human:approved
human:rejected
mvp0
```

---

### Group B — GitHub Apps

Status: In progress 🟡

Current progress:

```text
GitHub App setup guide created: plans/mvp0-github-apps-setup.md
Manual GitHub UI creation still required for the Apps and private keys.
```


#### B1. Create `trading-orchestrator-agent` GitHub App

Goal: Create Orchestrator identity.

Acceptance criteria:

- App exists.
- App is installed on target repo.
- App ID and installation ID are recorded.
- Private key is created and stored as a secret.

Permissions:

```text
Metadata: Read
Issues: Read/Write
Pull requests: Read
Checks: Read
Actions: Read
Contents: Read optional
Contents: Write disabled
```

---

#### B2. Create `trading-coding-agent` GitHub App

Goal: Create Coding Agent identity.

Acceptance criteria:

- App exists.
- App is installed on target repo.
- App ID and installation ID are recorded.
- Private key is created and stored as a secret.

Permissions:

```text
Metadata: Read
Contents: Read/Write
Issues: Read/Write
Pull requests: Read/Write
Checks: Read
Actions: Read
```

---

#### B3. Create `trading-review-agent` GitHub App

Goal: Create Review Agent identity.

Acceptance criteria:

- App exists.
- App is installed on target repo.
- App ID and installation ID are recorded.
- Private key is created and stored as a secret.

Permissions:

```text
Metadata: Read
Contents: Read
Pull requests: Read/Write
Checks: Read/Write
Issues: Read
Actions: Read
```

---

#### B4. Create `trading-validator-agent` GitHub App placeholder

Goal: Reserve the Validator identity even though Validator is out of MVP-0.

Acceptance criteria:

- App may exist but is not required by MVP-0 branch protection.
- If created, install it on the target repo and store metadata.
- No MVP-0 process depends on it.

---

#### B5. Implement GitHub App token helper

Goal: Create a reusable helper that mints installation tokens.

Acceptance criteria:

- CLI can mint token for `orchestrator`, `coding`, and `review`.
- Token is printed to stdout or exported for the current process only.
- Token is not written to workspace files.
- Helper fails loudly if the wrong Linux user tries to access a secret.

Example command:

```bash
trading-agent-token coding
trading-agent-token review
trading-agent-token orchestrator
```

---

### Group C — VM Bootstrap

#### C1. Create VM in GCP project

Goal: Create initial MVP-0 VM.

Acceptance criteria:

- Project: `atzmon-trading-project`
- VM name: `agent-hub-1`
- Initial machine type: `e2-standard-2`
- SSH/admin access works.
- No OpenClaw runtime installed as part of the trading execution plane.

---

#### C2. Install base packages

Goal: Install runtime dependencies.

Acceptance criteria:

Installed:

```text
git
gh
sqlite3
python3
node/npm if needed
Codex CLI
systemd service tooling
```

Verification:

```bash
git --version
gh --version
sqlite3 --version
codex --version
```

---

#### C3. Create Linux users

Goal: Create separate OS users for process isolation.

Acceptance criteria:

Users exist:

```text
agent-orchestrator
agent-coding
agent-review
agent-validator
```

Each user has a home directory and no unnecessary sudo permissions.

---

#### C4. Create `/agents` directory layout

Goal: Create role-specific directories.

Acceptance criteria:

```text
/agents/coding/controller
/agents/coding/workspaces
/agents/coding/logs
/agents/coding/state
/agents/review/workspaces
/agents/review/logs
/agents/review/state
/agents/validator/workspaces
/agents/validator/logs
/agents/validator/state
/agents/orchestrator/logs
/agents/orchestrator/state
/agents/orchestrator/backups
```

Ownership:

```text
/agents/coding/** owned by agent-coding
/agents/review/** owned by agent-review
/agents/validator/** owned by agent-validator
/agents/orchestrator/** owned by agent-orchestrator
```

---

#### C5. Create `/etc/trading-agents/config.yaml`

Goal: Store non-secret configuration.

Acceptance criteria:

Config includes:

```yaml
github:
  owner: atzmonpersonalassistant
  repo: trader
  default_branch: main

orchestrator:
  poll_interval_minutes: 10
  db_path: /agents/orchestrator/state/orchestrator.db
  backup_dir: /agents/orchestrator/backups

coding:
  max_concurrent_tasks: 2
  max_open_prs: 3
  max_review_fix_retries: 50

review:
  max_concurrent_prs: 2

merge:
  method: squash
  native_auto_merge_default: true
```

---

#### C6. Configure secrets access

Goal: Wire GCP Secret Manager or locked-down file fallback.

Acceptance criteria:

- Primary path uses GCP Secret Manager if available.
- Fallback path uses locked-down files only if needed.
- Each Linux user can access only its own GitHub App secret.
- Secrets are not readable from workspaces.

---

#### C7. Verify no OpenClaw runtime dependency

Goal: Ensure VM is independent from OpenClaw.

Acceptance criteria:

- No OpenClaw service is required for Orchestrator/Coding/Review startup.
- System can process GitHub polling without OpenClaw.
- WhatsApp relay absence does not stop core GitHub loop.

---

### Group D — Orchestrator Core

#### D1. Create Orchestrator CLI skeleton

Goal: Provide the main operator interface.

Acceptance criteria:

Commands exist:

```bash
trading-orchestrator status
trading-orchestrator scan
trading-orchestrator outbox next
trading-orchestrator inbox ack
trading-orchestrator db backup
```

Commands may be stubbed initially but must return structured output.

---

#### D2. Create SQLite schema

Goal: Store durable orchestrator state.

Acceptance criteria:

Tables exist:

```text
issues
pull_requests
events
locks
attempts
outbox
inbox
settings
```

Minimum fields include:

```text
external_id
state
labels
created_at
updated_at
last_seen_at
retry_count
```

---

#### D3. Implement SQLite backup command

Goal: Back up Orchestrator DB safely.

Acceptance criteria:

Command:

```bash
trading-orchestrator db backup
```

Uses SQLite `.backup`, not raw `cp` while DB is live.

Creates files like:

```text
/agents/orchestrator/backups/orchestrator-YYYYMMDD-HHMMSS.db
```

---

#### D4. Implement GitHub scan for ready issues

Goal: Find work for Coding Agent.

Acceptance criteria:

- Polls GitHub for issues with `agent:ready`.
- Ignores issues already claimed/in-progress/blocked.
- Writes discovered issues into SQLite.
- Does not dispatch yet.

---

#### D5. Implement issue claim transition

Goal: Safely claim one issue.

Acceptance criteria:

- Adds label `agent:claimed`.
- Removes or keeps `agent:ready` according to chosen state convention.
- Records lock in SQLite.
- Does not claim more than configured concurrency.

---

#### D6. Implement Coding Agent dispatch stub

Goal: Prove Orchestrator can call Coding Agent.

Acceptance criteria:

- Orchestrator can invoke a placeholder command under `agent-coding`.
- Placeholder writes a log and returns success/failure.
- Orchestrator records attempt.

---

#### D7. Implement PR detection

Goal: Detect PRs created by Coding Agent.

Acceptance criteria:

- Orchestrator scans open PRs from GitHub.
- Matches PRs to issues/branches.
- Records PR in SQLite.
- Adds/updates `agent:pr-opened` state.

---

#### D8. Implement auto-merge enablement

Goal: Orchestrator enables GitHub native auto-merge.

Acceptance criteria:

- For PRs without `needs:human-approval`, Orchestrator enables auto-merge.
- Merge method is squash.
- Does not enable auto-merge for rejected or human-gated PRs.
- Records action in SQLite event log.

---

#### D9. Implement Review failure routing

Goal: Route failed reviews back to Coding Agent.

Acceptance criteria:

- Detects failed Review Agent check.
- Increments review-fix retry count.
- If retry count < 50, labels `agent:needs-fix` and dispatches Coding Agent.
- If retry count >= 50, labels `agent:blocked` and creates outbox notification.
- No early-stop heuristics before the 50 cap.

---

#### D10. Implement outbox CLI

Goal: Allow OpenClaw to fetch messages for WhatsApp relay.

Acceptance criteria:

```bash
trading-orchestrator outbox next
```

Returns either:

```json
{"type":"none"}
```

or a structured message:

```json
{
  "type": "approval_request",
  "id": "outbox-123",
  "pr": 45,
  "title": "...",
  "body": "..."
}
```

---

#### D11. Implement inbox ack CLI

Goal: Allow OpenClaw to pass Uriel replies back.

Acceptance criteria:

```bash
trading-orchestrator inbox ack --outbox-id outbox-123 --decision approve
trading-orchestrator inbox ack --outbox-id outbox-123 --decision reject
```

For approvals:

- Adds label `human:approved`.
- Comments `/human-approved`.

For rejections:

- Adds label `human:rejected`.
- Comments `/human-rejected`.

---

### Group E — Coding Agent MVP

#### E1. Create Coding Agent CLI skeleton

Goal: Provide basic Coding Agent entry point.

Acceptance criteria:

Command exists:

```bash
trading-coding-agent run --issue <number>
```

It logs issue number, loads config, and exits cleanly.

---

#### E2. Implement issue workspace creation

Goal: Create isolated workspace per issue.

Acceptance criteria:

For issue 123:

```text
/agents/coding/workspaces/issue-123/
```

Workspace contains a repo checkout or git worktree.

---

#### E3. Implement branch creation

Goal: Create predictable agent branch.

Acceptance criteria:

Branch name format:

```text
agent/issue-123-short-slug
```

Branch is created from latest `main`.

---

#### E4. Implement Codex execution wrapper

Goal: Run Codex CLI inside the issue workspace.

Acceptance criteria:

- Runs `codex exec` from the issue workspace.
- Uses workspace-write sandbox.
- Uses approval mode `never` for MVP-0 worker execution.
- Captures stdout/stderr/logs.
- Does not leak secrets into prompt or workspace.

---

#### E5. Implement minimal code/doc change flow

Goal: Let Coding Agent complete a safe small issue.

Acceptance criteria:

- Reads issue title/body.
- Runs Codex with a constrained prompt.
- Produces a small diff.
- Runs minimal local verification if available.

---

#### E6. Implement commit and push

Goal: Push Coding Agent work to GitHub.

Acceptance criteria:

- Uses `trading-coding-agent` GitHub App token.
- Commits with clear author identity.
- Pushes only the agent branch, never `main`.
- Handles existing branch updates for fix retries.

---

#### E7. Implement PR creation

Goal: Open PR for completed issue.

Acceptance criteria:

- PR targets `main`.
- PR title references issue.
- PR body summarizes change and verification.
- PR includes link/reference to issue.
- PR is not manually merged by Coding Agent.

---

#### E8. Implement fix retry mode

Goal: Allow Coding Agent to respond to Review Agent failures.

Acceptance criteria:

Command supports:

```bash
trading-coding-agent run --issue <number> --fix-pr <pr-number>
```

It reads review comments/check output and updates the existing branch.

---

### Group F — Review Agent MVP

#### F1. Create Review Agent CLI skeleton

Goal: Provide basic Review Agent entry point.

Acceptance criteria:

Command exists:

```bash
trading-review-agent review --pr <number>
```

It logs PR number, loads config, and exits cleanly.

---

#### F2. Create PR review workspace

Goal: Create isolated workspace per PR.

Acceptance criteria:

For PR 45:

```text
/agents/review/workspaces/pr-45/
```

Workspace contains base/PR checkout or enough diff context.

---

#### F3. Fetch PR diff and metadata

Goal: Give reviewer the necessary context.

Acceptance criteria:

- Fetches PR title/body.
- Fetches changed files.
- Fetches diff.
- Fetches linked issue if available.

---

#### F4. Implement review checklist prompt

Goal: Standardize Review Agent behavior.

Acceptance criteria:

Checklist includes:

```text
- code quality
- test coverage or reasonable explanation
- no secrets
- no live trading changes without approval
- no risk/secrets/auth changes without approval
- no obviously unsafe behavior
- issue requirements addressed
```

---

#### F5. Run Review Agent analysis

Goal: Produce pass/fail review result.

Acceptance criteria:

- Runs selected review model/tool.
- Writes local `review.md`.
- Produces structured result: pass/fail/comment.

---

#### F6. Publish GitHub review/check

Goal: Make Review Agent blocking in GitHub.

Acceptance criteria:

- Uses `trading-review-agent` GitHub App token.
- Publishes check named `review-agent/pass` or equivalent stable required check name.
- Posts review/comment with summary.
- Failure gives actionable instructions for Coding Agent.

---

### Group G — Systemd and Scheduling

#### G1. Create Orchestrator systemd service/timer

Goal: Run Orchestrator polling every 10 minutes.

Acceptance criteria:

- systemd service runs as `agent-orchestrator`.
- timer triggers every 10 minutes.
- Logs go to `/agents/orchestrator/logs` and/or journald.
- Service does not require OpenClaw.

---

#### G2. Add manual operator commands

Goal: Allow manual debugging.

Acceptance criteria:

Commands documented:

```bash
trading-orchestrator status
trading-orchestrator scan
trading-orchestrator db backup
trading-coding-agent run --issue <number>
trading-review-agent review --pr <number>
```

---

#### G3. Add log locations and rotation

Goal: Prevent unbounded logs.

Acceptance criteria:

- Log paths documented.
- Basic log rotation configured.
- Failed worker logs are preserved per issue/PR.

---

### Group H — Human Approval Relay

#### H1. Define approval request payload

Goal: Standardize messages from Orchestrator to OpenClaw.

Acceptance criteria:

Outbox approval request includes:

```text
outbox id
PR number
PR title
reason approval is required
short risk summary
GitHub URL
allowed replies: approve/reject
```

---

#### H2. Implement approval request creation

Goal: Queue human approval request when a PR is gated.

Acceptance criteria:

- PR with `needs:human-approval` is not auto-merged.
- Orchestrator creates outbox approval request.
- Duplicate requests are deduped.

---

#### H3. Implement approval response handling

Goal: Convert Uriel's WhatsApp response into GitHub state.

Acceptance criteria:

Approve:

```text
label human:approved
comment /human-approved
```

Reject:

```text
label human:rejected
comment /human-rejected
```

---

### Group I — MVP-0 End-to-End Test

#### I1. Create safe test issue

Goal: Provide first real task.

Acceptance criteria:

- Issue is small and low-risk.
- Issue is labeled `agent:ready` and `mvp0`.
- Example: add a small README section, add a simple healthcheck script, or add a tiny unit test.

---

#### I2. Run Orchestrator scan manually

Goal: Confirm issue discovery.

Acceptance criteria:

```bash
trading-orchestrator scan
```

- Finds issue.
- Claims issue.
- Dispatches Coding Agent or prepares dispatch state.

---

#### I3. Verify Coding Agent PR creation

Goal: Confirm Coding Agent can produce a PR.

Acceptance criteria:

- Branch exists.
- PR exists.
- PR references issue.
- PR is not merged before Review Agent required check passes.

---

#### I4. Verify Review Agent required check

Goal: Confirm review gates merge.

Acceptance criteria:

- Review Agent check appears on PR.
- If pass, GitHub branch protection sees it.
- If fail, Orchestrator routes back to Coding Agent.

---

#### I5. Verify GitHub native auto-merge

Goal: Confirm GitHub performs final merge.

Acceptance criteria:

- Orchestrator enables auto-merge.
- GitHub waits for required checks.
- GitHub squash-merges PR.
- Main branch receives one commit.

---

#### I6. Verify cleanup

Goal: Confirm no resource leak after merge.

Acceptance criteria:

- Orchestrator marks issue/PR complete.
- Coding workspace can be archived or cleaned.
- Review workspace can be archived or cleaned.
- SQLite state records final status.

---

## 4. Suggested Implementation Order

1. A1 target repo confirmation
2. A4 labels
3. B1-B3 GitHub Apps
4. C1-C6 VM bootstrap
5. D1-D3 Orchestrator CLI + DB + backup
6. B5 token helper
7. D4-D6 issue scan/claim/dispatch stub
8. E1-E4 Coding Agent skeleton/workspace/Codex wrapper
9. E6-E7 commit/push/PR creation
10. F1-F6 Review Agent MVP
11. A2-A3 branch protection + squash/auto-merge setup
12. D7-D9 PR detection/auto-merge/retry routing
13. G1-G3 systemd/logging
14. H1-H3 approval relay
15. I1-I6 end-to-end test

---

## 5. MVP-0 Completion Criteria

MVP-0 is complete when:

- A GitHub issue labeled `agent:ready` is picked up by Orchestrator.
- Coding Agent creates a dedicated workspace and branch.
- Coding Agent opens a PR.
- Orchestrator enables GitHub native auto-merge.
- Review Agent runs as a required check.
- Failed review routes back to Coding Agent automatically.
- Passing review allows GitHub to squash-merge the PR.
- Orchestrator records the final state in SQLite.
- OpenClaw is not required for the loop except optional WhatsApp relay.

---

## 6. Explicit Non-Goals for MVP-0

- No Quant Validator.
- No QuantConnect integration.
- No strategy performance judgment.
- No paper/live trading.
- No broker integration.
- No OpenClaw runtime dependency on the VM.
- No HTTP API between OpenClaw and Orchestrator.
- No webhooks from GitHub to the VM.
