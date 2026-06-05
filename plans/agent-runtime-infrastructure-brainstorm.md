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

The system should keep four logical agent roles:

1. **Coding Agent**
   - Writes code.
   - Works on GitHub issues.
   - Opens branches and PRs.
   - Fixes CI/review comments.

2. **Review Agent**
   - Reviews PR diffs.
   - Checks code quality, tests, secrets, and implementation safety.
   - Performs a quant-specific PR checklist where relevant.
   - Should be independent from the Coding Agent session.

3. **Quant Research Validator Agent**
   - Reviews backtest/sweep results.
   - Looks for overfitting, weak baselines, bad risk assumptions, and unstable performance.
   - Decides whether research is ready for paper promotion.
   - Can mark issues as `agent:ready` when evidence is sufficient.

4. **Reporting / Orchestration Agent**
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

## 12. Open Questions

1. Should the runtime be OpenClaw, Hermes, or a small custom daemon?
2. Should the two GitHub identities be machine users or GitHub Apps?
3. Can Codex/Claude subscriptions be used safely for daemonized automation, or is API billing required?
4. What hard monthly budget cap should be enforced for each model/backend?
5. Should Governance ever be allowed to auto-merge, or only approve/check while GitHub auto-merge completes?
6. Should Builder be allowed to run QuantConnect jobs, or should only Governance/CI run them?
7. What is the minimal first autonomous workflow to prove value?

---

## 13. Suggested Next Step

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
