# MVP-0 Task Breakdown — Agentic Dev Loop

Status: Draft
Owner: Uriel
Scope: MVP-0 only

---

## 1. MVP-0 Goal

Prove the agentic development loop on a real GitHub repo without QuantConnect and without a Quant Validator.

Smoke-check note: dummy agent-loop issue #7 was processed as a documentation-only MVP-0 loop verification task.
Smoke-check note: issue #13 verified the real coding/review/orchestrator loop after VPS deployment and cleanup timers were enabled, using a documentation-only change.

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

Status: Completed ✅

Completed evidence:

```text
GitHub App setup guide: plans/mvp0/github-apps-setup.md
Manifest helper: tools/github_app_manifest_flow.py
Token helper: tools/trading_agent_token.py

trading-orchestrator-agent app_id=3988813 installation_id=138640121
trading-coding-agent       app_id=3988816 installation_id=138640143
trading-review-agent       app_id=3988836 installation_id=138640182
trading-validator-agent    app_id=3988837 installation_id=138640218

Private keys saved outside git under ~/.trading-agents/github-apps/*.private-key.pem
Installation tokens successfully minted for all four Apps.
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

Status: Completed ✅

Current evidence:

```text
Provider: OVHcloud VPS
Host: vps-ce2ba5e7.vps.ovh.ca
IPv4: 144.217.82.149
OS: Ubuntu 26.04 LTS
Admin user: ubuntu
Access: SSH key ~/.ssh/ovh_vps_ce2ba5e7 on the assistant Mac
Installed base packages: git, gh, sqlite3, python3, node/npm, Codex CLI, jq, curl, rsync
Agent Linux users: created with no sudo
/agents layout: created with role-specific ownership; /agents is traverse-only so role users can enter their owned subtree
Config: /etc/trading-agents/config.yaml
OpenClaw runtime on VM: not installed
```

C6 secrets implementation:

```text
MVP-0 uses the approved locked-down VM files fallback, not GCP Secret Manager yet.
Private keys are stored under /etc/trading-agents/secrets/<role>/private-key.pem.
Each key directory is owned by its matching Linux user only.
The root secrets directory is traverse-only for non-root users.
/usr/local/bin/trading-agent-token mints short-lived GitHub App installation tokens.
The helper refuses to mint a role token unless run as the matching agent user.
Token minting was verified for orchestrator, coding, review, and validator.
Cross-role minting was verified to fail.
```

#### C1. Create initial MVP-0 VM — Completed ✅

Goal: Create initial MVP-0 VM.

Acceptance criteria:

- Provider and host are recorded.
- SSH/admin access works.
- Machine has enough RAM/disk for MVP-0 agent loop.
- No OpenClaw runtime installed as part of the trading execution plane.

Actual MVP-0 VM:

```yaml
vm:
  provider: ovhcloud
  host: vps-ce2ba5e7.vps.ovh.ca
  ipv4: 144.217.82.149
  os: Ubuntu 26.04 LTS
  admin_user: ubuntu
  ssh_key: ~/.ssh/ovh_vps_ce2ba5e7
```

---

#### C2. Install base packages — Completed ✅

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

#### C3. Create Linux users — Completed ✅

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

#### C4. Create `/agents` directory layout — Completed ✅

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

#### C5. Create `/etc/trading-agents/config.yaml` — Completed ✅

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

#### C6. Configure secrets access — Completed ✅

Goal: Wire GCP Secret Manager or locked-down file fallback.

Acceptance criteria:

- Primary path uses GCP Secret Manager if available.
- Fallback path uses locked-down files only if needed.
- Each Linux user can access only its own GitHub App secret.
- Secrets are not readable from workspaces.

---

#### C7. Verify no OpenClaw runtime dependency — Completed ✅

Goal: Ensure VM is independent from OpenClaw.

Acceptance criteria:

- No OpenClaw service is required for Orchestrator/Coding/Review startup.
- System can process GitHub polling without OpenClaw.
- WhatsApp relay absence does not stop core GitHub loop.

---

### Group D — Orchestrator Core

Status: In progress

Current implementation:

```text
D1-D3 implemented in tools/trading_orchestrator.py and tools/trading-orchestrator.
CLI skeleton returns structured JSON.
SQLite schema creates issues, pull_requests, events, locks, attempts, outbox, inbox, settings.
Backup command uses sqlite3 Connection.backup(), not raw cp.
DB and backup files are mode 600 and owned by agent-orchestrator.
D4 GitHub issue scan is implemented and verified against GitHub on the VM; current repo has 0 open agent:ready issues.
D5 issue claim transition is implemented and verified on GitHub issue #3.
D6 Coding Agent dispatch stub is implemented and verified on VM issue #3; agent-orchestrator can run the stub as agent-coding through a narrow sudoers rule.
D7 PR detection is implemented and verified on VM against PR #1. PR state is recorded in SQLite with agent:pr-opened; external GitHub PR label mutation returned 403 for the Orchestrator App and is reported as non-fatal.
D8 auto-merge enablement is implemented and verified on PR #1. The Orchestrator App now has Contents: write, Pull requests: write, and Administration: read. GitHub native auto-merge was enabled by app/trading-orchestrator-agent with SQUASH.
D9 review failure routing is implemented and verified on VM using a synthetic failing review-agent/pass check-run on PR #1. The Orchestrator labels PRs agent:needs-fix, increments retry_count, records review_failure_routed events, and dispatches the Coding Agent stub while retry_count <= 50.
D10 outbox CLI is implemented and verified locally and on the VM. `trading-orchestrator outbox next` now returns `{"type":"none"}` when empty, or a structured pending message including type/id/body/channel and payload fields such as pr/title/url.
D11 inbox ack CLI is implemented and verified locally against PR #1: approve marks outbox acknowledged, inserts an acknowledged inbox record, adds human:approved, and comments /human-approved. The updated command is deployed on the VM.
E1 Coding Agent CLI skeleton is implemented and verified locally and on the VM under agent-coding. `trading-coding-agent run --issue 123` loads config, writes `/agents/coding/logs/coding-agent.jsonl`, and exits cleanly.
E2 issue workspace creation is implemented and verified locally and on the VM. `trading-coding-agent run --issue N` now creates `/agents/coding/workspaces/issue-N/` as a git checkout from `main`, using a short-lived Coding App token for private GitHub HTTPS clone and then resetting `origin` to the clean non-token URL.
E3 branch creation is implemented and verified on the VM. The Coding Agent creates `agent/issue-<n>-<slug>` from fresh `main`.
E4 Codex execution wrapper is implemented and production-verified on the VM after installing locked-down Codex auth for `agent-coding`. It runs `codex exec --sandbox workspace-write -c approval_policy="never"`, captures stdout/stderr/logs, and does not print secrets.
E5 minimal code/doc change flow is production-verified on issue #3: Codex edited `plans/mvp0/task-breakdown.md` with a small documentation change and `git diff --check` passed.
E6 commit and push is implemented and verified on the VM using the Coding App token. It committed `ce3ef11` to `agent/issue-3-mvp-0-test-orchestrator-claim-flow` and never pushed main. Existing branch update uses explicit `--force-with-lease=<ref>:<sha>`.
E7 PR creation is implemented and verified on the VM: the Coding App opened/updated PR #4 targeting main.
E8 fix retry mode is implemented and verified on PR #4: `trading-coding-agent run --issue 3 --fix-pr 4` read review context, checked out the existing PR branch, updated it, and pushed with explicit force-with-lease.
F1-F6 Review Agent MVP is implemented and verified on PR #4. `trading-review-agent review --pr 4` creates `/agents/review/workspaces/pr-4/`, fetches PR metadata/files/diff, uses the standard checklist, runs Codex review, writes `.review-agent/review.md`, posts a PR comment, and publishes the required `review-agent/pass` check. A first review failed with actionable feedback; after E8 retry, review passed and published a success check.
G1 Orchestrator systemd service/timer is implemented on the VM. `trading-orchestrator.timer` is enabled and active, runs every 10 minutes as `agent-orchestrator`, uses a flock lock, and logs to `/agents/orchestrator/logs/tick.log`.
G2 manual operator commands are documented in `plans/mvp0/operator-runbook.md`.
G3 log locations and rotation are documented in the runbook and deployed on the VM as `/etc/logrotate.d/trading-agents`; `logrotate -d` validates the config.
H1 approval request payload is defined in the runbook and implemented in Orchestrator outbox payloads.
H2 approval request creation is implemented in `enable-auto-merge`: PRs labeled `needs:human-approval` without `human:approved` are skipped and deduped into `approval-pr-<n>` outbox messages.
H3 approval response handling is implemented in `inbox ack`, adding human approval/rejection labels and comments.
I1-I6 E2E test completed with issue #5 and PR #6: issue was created with `agent:ready,mvp0`, scan/claim found it, Coding Agent opened PR #6, Review Agent published passing `review-agent/pass`, GitHub squash-merged PR #6, and `finalize-merged` marked PR #6 merged and issue #5 closed in SQLite/GitHub. Edge case: when checks were already clean, GitHub rejected auto-merge enablement as `Pull request is in clean status`, so the final merge was executed with GitHub squash merge to complete the E2E validation.
MVP-0 completion validation is complete except PR #1 still contains accumulated implementation work and remains open/behind for review/merge hygiene.
```


#### D1. Create Orchestrator CLI skeleton — Completed ✅

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

#### D2. Create SQLite schema — Completed ✅

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

#### D3. Implement SQLite backup command — Completed ✅

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

#### D4. Implement GitHub scan for ready issues — Completed ✅

Goal: Find work for Coding Agent.

Acceptance criteria:

- Polls GitHub for issues with `agent:ready`.
- Ignores issues already claimed/in-progress/blocked.
- Writes discovered issues into SQLite.
- Does not dispatch yet.

---

#### D5. Implement issue claim transition — Completed ✅

Goal: Safely claim one issue.

Acceptance criteria:

- Adds label `agent:claimed`.
- Removes label `agent:ready`; MVP-0 claim state is represented by `agent:claimed` only.
- Records lock in SQLite.
- Does not claim more than configured concurrency.

Issue #3 verification target: Orchestrator claim flow removes `agent:ready`, adds `agent:claimed`, and records the SQLite lock.
MVP-0 test record: use this transition as the D5 acceptance check before dispatching any Coding Agent work.

---

#### D6. Implement Coding Agent dispatch stub — Completed ✅

Goal: Prove Orchestrator can call Coding Agent.

Acceptance criteria:

- Orchestrator can invoke a placeholder command under `agent-coding`.
- Placeholder writes a log and returns success/failure.
- Orchestrator records attempt.

---

#### D7. Implement PR detection — Completed ✅

Goal: Detect PRs created by Coding Agent.

Acceptance criteria:

- Orchestrator scans open PRs from GitHub.
- Matches PRs to issues/branches.
- Records PR in SQLite.
- Adds/updates `agent:pr-opened` state.

---

#### D8. Implement auto-merge enablement — Completed ✅

Goal: Orchestrator enables GitHub native auto-merge.

Acceptance criteria:

- For PRs without `needs:human-approval`, Orchestrator enables auto-merge.
- Merge method is squash.
- Does not enable auto-merge for rejected or human-gated PRs.
- Records action in SQLite event log.

---

#### D9. Implement Review failure routing — Completed ✅

Goal: Route failed reviews back to Coding Agent.

Acceptance criteria:

- Detects failed Review Agent check.
- Increments review-fix retry count.
- If retry count < 50, labels `agent:needs-fix` and dispatches Coding Agent.
- If retry count >= 50, labels `agent:blocked` and creates outbox notification.
- No early-stop heuristics before the 50 cap.

---

#### D10. Implement outbox CLI — Completed ✅

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

#### D11. Implement inbox ack CLI — Completed ✅

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

#### E1. Create Coding Agent CLI skeleton — Completed ✅

Goal: Provide basic Coding Agent entry point.

Acceptance criteria:

Command exists:

```bash
trading-coding-agent run --issue <number>
```

It logs issue number, loads config, and exits cleanly.

---

#### E2. Implement issue workspace creation — Completed ✅

Goal: Create isolated workspace per issue.

Acceptance criteria:

For issue 123:

```text
/agents/coding/workspaces/issue-123/
```

Workspace contains a repo checkout or git worktree.

---

#### E3. Implement branch creation — Completed ✅

Goal: Create predictable agent branch.

Acceptance criteria:

Branch name format:

```text
agent/issue-123-short-slug
```

Branch is created from latest `main`.

---

#### E4. Implement Codex execution wrapper — Completed ✅

Goal: Run Codex CLI inside the issue workspace.

Acceptance criteria:

- Runs `codex exec` from the issue workspace.
- Uses workspace-write sandbox.
- Uses approval mode `never` for MVP-0 worker execution.
- Captures stdout/stderr/logs.
- Does not leak secrets into prompt or workspace.

---

#### E5. Implement minimal code/doc change flow — Completed ✅

Goal: Let Coding Agent complete a safe small issue.

Acceptance criteria:

- Reads issue title/body.
- Runs Codex with a constrained prompt.
- Produces a small diff.
- Runs minimal local verification if available.

---

#### E6. Implement commit and push — Completed ✅

Goal: Push Coding Agent work to GitHub.

Acceptance criteria:

- Uses `trading-coding-agent` GitHub App token.
- Commits with clear author identity.
- Pushes only the agent branch, never `main`.
- Handles existing branch updates for fix retries.

---

#### E7. Implement PR creation — Completed ✅

Goal: Open PR for completed issue.

Acceptance criteria:

- PR targets `main`.
- PR title references issue.
- PR body summarizes change and verification.
- PR includes link/reference to issue.
- PR is not manually merged by Coding Agent.

---

#### E8. Implement fix retry mode — Completed ✅

Goal: Allow Coding Agent to respond to Review Agent failures.

Acceptance criteria:

Command supports:

```bash
trading-coding-agent run --issue <number> --fix-pr <pr-number>
```

It reads review comments/check output and updates the existing branch.

---

### Group F — Review Agent MVP

#### F1. Create Review Agent CLI skeleton — Completed ✅

Goal: Provide basic Review Agent entry point.

Acceptance criteria:

Command exists:

```bash
trading-review-agent review --pr <number>
```

It logs PR number, loads config, and exits cleanly.

---

#### F2. Create PR review workspace — Completed ✅

Goal: Create isolated workspace per PR.

Acceptance criteria:

For PR 45:

```text
/agents/review/workspaces/pr-45/
```

Workspace contains base/PR checkout or enough diff context.

---

#### F3. Fetch PR diff and metadata — Completed ✅

Goal: Give reviewer the necessary context.

Acceptance criteria:

- Fetches PR title/body.
- Fetches changed files.
- Fetches diff.
- Fetches linked issue if available.

---

#### F4. Implement review checklist prompt — Completed ✅

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

#### F5. Run Review Agent analysis — Completed ✅

Goal: Produce pass/fail review result.

Acceptance criteria:

- Runs selected review model/tool.
- Writes local `review.md`.
- Produces structured result: pass/fail/comment.

---

#### F6. Publish GitHub review/check — Completed ✅

Goal: Make Review Agent blocking in GitHub.

Acceptance criteria:

- Uses `trading-review-agent` GitHub App token.
- Publishes check named `review-agent/pass` or equivalent stable required check name.
- Posts review/comment with summary.
- Failure gives actionable instructions for Coding Agent.

---

### Group G — Systemd and Scheduling

#### G1. Create Orchestrator systemd service/timer — Completed ✅

Goal: Run Orchestrator polling every 10 minutes.

Acceptance criteria:

- systemd service runs as `agent-orchestrator`.
- timer triggers every 10 minutes.
- Logs go to `/agents/orchestrator/logs` and/or journald.
- Service does not require OpenClaw.

---

#### G2. Add manual operator commands — Completed ✅

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

#### G3. Add log locations and rotation — Completed ✅

Goal: Prevent unbounded logs.

Acceptance criteria:

- Log paths documented.
- Basic log rotation configured.
- Failed worker logs are preserved per issue/PR.

---

### Group H — Human Approval Relay

#### H1. Define approval request payload — Completed ✅

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

#### H2. Implement approval request creation — Completed ✅

Goal: Queue human approval request when a PR is gated.

Acceptance criteria:

- PR with `needs:human-approval` is not auto-merged.
- Orchestrator creates outbox approval request.
- Duplicate requests are deduped.

---

#### H3. Implement approval response handling — Completed ✅

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

Operator runbook pointer: use G2 for manual commands, G3 for log locations/rotation, and I1-I6 below as the MVP-0 end-to-end execution checklist.

#### I1. Create safe test issue — Completed ✅

Goal: Provide first real task.

Acceptance criteria:

- Issue is small and low-risk.
- Issue is labeled `agent:ready` and `mvp0`.
- Example: add a small README section, add a simple healthcheck script, or add a tiny unit test.

---

#### I2. Run Orchestrator scan manually — Completed ✅

Goal: Confirm issue discovery.

Acceptance criteria:

```bash
trading-orchestrator scan
```

- Finds issue.
- Claims issue.
- Dispatches Coding Agent or prepares dispatch state.

---

#### I3. Verify Coding Agent PR creation — Completed ✅

Goal: Confirm Coding Agent can produce a PR.

Acceptance criteria:

- Branch exists.
- PR exists.
- PR references issue.
- PR is not merged before Review Agent required check passes.

---

#### I4. Verify Review Agent required check — Completed ✅

Goal: Confirm review gates merge.

Acceptance criteria:

- Review Agent check appears on PR.
- If pass, GitHub branch protection sees it.
- If fail, Orchestrator routes back to Coding Agent.

---

#### I5. Verify GitHub native auto-merge — Completed ✅

Goal: Confirm GitHub performs final merge.

Acceptance criteria:

- Orchestrator enables auto-merge.
- GitHub waits for required checks.
- GitHub squash-merges PR.
- Main branch receives one commit.

---

#### I6. Verify cleanup — Completed ✅

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

<!-- autoreview integration smoke 2026-06-09T09:39:57Z -->
