# MVP-0 GitHub Apps Setup

Status: Draft / setup guide
Scope: Group B of MVP-0
Repo: `atzmonpersonalassistant/trader`

---

## 1. Goal

Create four GitHub Apps for the trading-agent platform. These Apps are GitHub identities for automation; they replace separate GitHub user accounts.

Apps:

```text
trading-orchestrator-agent
trading-coding-agent
trading-review-agent
trading-validator-agent
```

MVP-0 actively needs:

```text
trading-orchestrator-agent
trading-coding-agent
trading-review-agent
```

`trading-validator-agent` is a placeholder for MVP-1+ and should not be required by MVP-0 branch protection.

---

## 2. Shared App Settings

For each App:

```text
Homepage URL: https://github.com/atzmonpersonalassistant/trader
Webhook: disabled for MVP-0
Where can this GitHub App be installed: Only on this account
Install on: atzmonpersonalassistant/trader only
```

Webhook is intentionally disabled because MVP-0 uses Orchestrator polling every 10 minutes.

After creating each App:

1. Record App ID.
2. Install App on `atzmonpersonalassistant/trader`.
3. Record Installation ID.
4. Generate one private key.
5. Store the private key in GCP Secret Manager or locked-down VM fallback.
6. Do not commit private keys to the repo.

---

## 3. App: `trading-orchestrator-agent`

Purpose:

- Poll issues/PRs/checks/actions.
- Update labels/comments for lifecycle state.
- Enable GitHub native auto-merge when allowed.
- Write operational follow-up issues/comments.
- No code writes.

Permissions:

```text
Metadata: Read
Issues: Read and write
Pull requests: Read
Checks: Read
Actions: Read
Contents: Read only, optional
Contents: Write: disabled
```

Events/webhook subscriptions:

```text
None for MVP-0
```

Expected runtime Linux user:

```text
agent-orchestrator
```

Secret name suggestion:

```text
github-app-trading-orchestrator-agent-private-key
```

---

## 4. App: `trading-coding-agent`

Purpose:

- Read assigned issues.
- Create/update branches.
- Commit/push code/docs/tests.
- Open/update PRs.
- Respond to review failures.
- Never push to `main`.

Permissions:

```text
Metadata: Read
Contents: Read and write
Issues: Read and write
Pull requests: Read and write
Checks: Read
Actions: Read
```

Events/webhook subscriptions:

```text
None for MVP-0
```

Expected runtime Linux user:

```text
agent-coding
```

Secret name suggestion:

```text
github-app-trading-coding-agent-private-key
```

---

## 5. App: `trading-review-agent`

Purpose:

- Read PR diff/metadata.
- Read code.
- Publish required Review Agent check.
- Post PR review/comment.
- Does not push code.

Permissions:

```text
Metadata: Read
Contents: Read
Pull requests: Read and write
Checks: Read and write
Issues: Read
Actions: Read
```

Events/webhook subscriptions:

```text
None for MVP-0
```

Expected runtime Linux user:

```text
agent-review
```

Secret name suggestion:

```text
github-app-trading-review-agent-private-key
```

Required check name for MVP-0 branch protection:

```text
review-agent/pass
```

---

## 6. App: `trading-validator-agent`

Purpose:

- Placeholder for MVP-1+ Quant Validator.
- Not active in MVP-0.
- Not required by MVP-0 branch protection.

Suggested future permissions:

```text
Metadata: Read
Contents: Read
Pull requests: Read and write
Checks: Read and write
Issues: Read and write
Actions: Read
```

Events/webhook subscriptions:

```text
None for MVP-0
```

Expected runtime Linux user:

```text
agent-validator
```

Secret name suggestion:

```text
github-app-trading-validator-agent-private-key
```

---

## 7. Values to Record After Creation

Create `/etc/trading-agents/config.yaml` later with non-secret IDs:

```yaml
github:
  owner: atzmonpersonalassistant
  repo: trader
  default_branch: main

apps:
  orchestrator:
    app_slug: trading-orchestrator-agent
    app_id: "TODO"
    installation_id: "TODO"
    private_key_secret: github-app-trading-orchestrator-agent-private-key

  coding:
    app_slug: trading-coding-agent
    app_id: "TODO"
    installation_id: "TODO"
    private_key_secret: github-app-trading-coding-agent-private-key

  review:
    app_slug: trading-review-agent
    app_id: "TODO"
    installation_id: "TODO"
    private_key_secret: github-app-trading-review-agent-private-key

  validator:
    app_slug: trading-validator-agent
    app_id: "TODO"
    installation_id: "TODO"
    private_key_secret: github-app-trading-validator-agent-private-key
```

---

## 8. Manual Creation Links

GitHub Apps for a personal account are created in the GitHub UI:

```text
https://github.com/settings/apps/new
```

Use the settings in this document for each App.

After installation, verify Apps are installed on the repo:

```bash
gh api repos/atzmonpersonalassistant/trader/installation
```

Note: depending on token scopes, `gh api user/installations` may not work with the current PAT. This does not necessarily mean the App installation failed.

---

## 9. Completion Criteria for Group B

Group B is complete when:

- `trading-orchestrator-agent` exists and is installed on `trader`.
- `trading-coding-agent` exists and is installed on `trader`.
- `trading-review-agent` exists and is installed on `trader`.
- `trading-validator-agent` exists or is explicitly deferred.
- App IDs and Installation IDs are recorded in config.
- Private keys are stored as secrets, not in git.
- Token helper can mint installation tokens for orchestrator/coding/review.

---

## 10. Prepared Manifest Flow Helper

A helper script is available:

```bash
python3 agent-platform/tools/github_app_manifest_flow.py serve
```

Then open:

```text
http://127.0.0.1:8787/
```

The helper prepares GitHub App manifests for all four Apps:

```text
trading-orchestrator-agent
trading-coding-agent
trading-review-agent
trading-validator-agent
```

The fourth App, `trading-validator-agent`, is included even though it is not active in MVP-0. Creating it now completes the identity set and avoids reopening GitHub App setup later.

After GitHub redirects back to the local helper, the helper converts the manifest code and saves outputs outside git:

```text
~/.trading-agents/github-apps/<role>.private-key.pem
~/.trading-agents/github-apps/<role>.app.json
```

Do not commit these files.

Manifest helper note: the manifest intentionally omits webhook/hook attributes. MVP-0 uses polling only, and GitHub rejects localhost webhook URLs even when the intended webhook flow is inactive.

---

## 11. Created Apps and Installation IDs

Created on 2026-06-07.

```yaml
apps:
  orchestrator:
    app_slug: trading-orchestrator-agent
    app_id: 3988813
    installation_id: 138640121
    private_key_local_path: ~/.trading-agents/github-apps/orchestrator.private-key.pem

  coding:
    app_slug: trading-coding-agent
    app_id: 3988816
    installation_id: 138640143
    private_key_local_path: ~/.trading-agents/github-apps/coding.private-key.pem

  review:
    app_slug: trading-review-agent
    app_id: 3988836
    installation_id: 138640182
    private_key_local_path: ~/.trading-agents/github-apps/review.private-key.pem

  validator:
    app_slug: trading-validator-agent
    app_id: 3988837
    installation_id: 138640218
    private_key_local_path: ~/.trading-agents/github-apps/validator.private-key.pem
```

Private keys are intentionally stored outside git and must later be moved to GCP Secret Manager or locked-down VM secrets.

Installation token helper:

```bash
python3 agent-platform/tools/trading_agent_token.py orchestrator
python3 agent-platform/tools/trading_agent_token.py coding
python3 agent-platform/tools/trading_agent_token.py review
python3 agent-platform/tools/trading_agent_token.py validator
```

Token minting has been verified for all four Apps.
