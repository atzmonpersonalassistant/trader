# MVP-0 Cost Plan

Status: Draft
Scope: Trading agent platform MVP-0

---

## 1. Purpose

Track the expected recurring and variable costs for the MVP-0 trading-agent infrastructure.

MVP-0 scope:

```text
issue -> Coding Agent -> PR -> Review Agent required check -> GitHub native auto-merge
```

MVP-0 does not include QuantConnect sweeps, paper trading, live trading, or broker integration.

---

## 2. Expected Monthly Costs

| Item | Expected cost | Notes |
| --- | ---: | --- |
| GitHub Pro / paid private repo features | ~$4-5/month | Needed for branch protection, required checks, and native auto-merge on private repo. Billing screen is source of truth. |
| GCP VM `agent-hub-1` (`e2-standard-2`) | ~<$50/month before disk/log/network | Always-on VM estimate; exact price depends on region, disk, sustained-use discounts, and uptime. |
| Persistent disk | TBD | Depends on boot disk size/type and any extra workspace/artifact disk. |
| GCP Secret Manager | Usually $0 to low dollars/month | Free tier covers small usage; beyond free tier is low cost. Cache secrets per process to avoid unnecessary access calls. |
| GitHub Actions | Usually included initially | GitHub Pro includes more private Actions minutes than Free. Monitor usage. |
| Codex/OpenAI usage | TBD / variable | Likely the main variable cost once agents run often. Needs budget tracking. |
| Network/logging overhead | Low/TBD | Depends on logs, artifact transfer, and package downloads. |

---

## 3. GitHub Paid Plan Rationale

The repo is currently private. On GitHub Free, private repos may not support the branch protection / required-check workflow needed for MVP-0.

Required MVP-0 capabilities:

```text
- protected main branch
- required Review Agent check
- GitHub native auto-merge
- squash merge
```

The paid GitHub feature cost is worth it because it lets GitHub be the central guardrail instead of building a weaker custom merge gate.

### Can the ~$5/month be reduced without annual commitment?

Probably not meaningfully.

Options:

1. **Pay monthly GitHub Pro / paid plan**
   - Best fit if keeping the repo private.
   - Expected around $4-5/month.
   - No annual commitment.

2. **Annual billing**
   - May reduce the effective monthly cost if GitHub offers an annual discount.
   - Requires upfront/annual commitment.

3. **Make repo public**
   - Can unlock branch protection features without paying for private-repo advanced controls.
   - Not recommended if code, strategy logic, infra details, or trading plans should stay private.

4. **Custom merge gate workaround**
   - Avoids GitHub Pro but undermines the desired design.
   - More implementation work and less trustworthy than GitHub branch protection.

Decision bias: pay monthly if the repo should remain private.

---

## 4. Cost Controls

### GitHub

- Use GitHub native auto-merge and required checks to avoid custom infrastructure.
- Watch Actions minutes.
- Keep CI lightweight for MVP-0.

### GCP VM

- Start with one VM only: `agent-hub-1`.
- Initial type: `e2-standard-2`.
- Do not split agents into separate VMs until load/security requires it.
- Add GCP budget alerts before running 24/7 production loops.

### Secret Manager

- Store secrets in GCP Secret Manager by default.
- Cache secret values in process memory for each run rather than calling Secret Manager repeatedly in tight loops.
- Fallback to locked-down VM files only if billing/setup blocks progress.

### Codex/OpenAI

- Start with small concurrency:
  - `max_concurrent_tasks = 2`
  - `max_open_prs = 3`
- Review-fix retry cap is 50 by decision, but usage should still be observable.
- Add reporting for tokens/usage/cost where available.

---

## 5. Open Cost Questions

- Exact GitHub billing price shown in Uriel's account.
- Exact GCP VM region and disk size.
- Codex/OpenAI pricing and usage limits for the selected model(s).
- Whether GitHub Actions minutes will stay inside included quota.
- Whether QuantConnect costs enter MVP-1.

---

## 6. Current Recommendation

For MVP-0:

```text
Keep repo private.
Pay monthly for GitHub private branch protection/required checks.
Use one GCP VM.
Use Secret Manager unless it blocks setup.
Add budget alerts before always-on operation.
```

The extra GitHub cost is small relative to the value of reliable branch protection and native auto-merge.
