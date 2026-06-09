#!/usr/bin/env python3
"""MVP-0 Coding Agent CLI.

The MVP agent creates an isolated issue workspace, creates a predictable branch,
runs a constrained Codex invocation, verifies minimally, commits/pushes the
result, and opens a PR. It is intentionally conservative and branch-only: it
never pushes main.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(os.environ.get("TRADING_CODING_CONFIG", "/agents/coding/config.json"))
DEFAULT_LOG_DIR = Path(os.environ.get("TRADING_CODING_LOG_DIR", "/agents/coding/logs"))
DEFAULT_TOKEN_CMD = os.environ.get("TRADING_AGENT_TOKEN_CMD", "trading-agent-token")

DEFAULT_CONFIG: dict[str, Any] = {
    "agent": "coding",
    "repo": "atzmonpersonalassistant/trader",
    "base_branch": "main",
    "workspace_root": "/agents/coding/workspaces",
    "token_cmd": DEFAULT_TOKEN_CMD,
    "codex_model": "gpt-5.5",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_config(path: Path) -> tuple[dict[str, Any], bool]:
    if not path.exists():
        return dict(DEFAULT_CONFIG), False
    with path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    config = dict(DEFAULT_CONFIG)
    config.update(loaded)
    return config, True


def repo_parts(config: dict[str, Any]) -> tuple[str, str]:
    owner, repo = str(config["repo"]).split("/", 1)
    return owner, repo


def repo_clone_url(config: dict[str, Any]) -> str:
    if config.get("repo_url"):
        return str(config["repo_url"])
    return f"https://github.com/{config['repo']}.git"


def mint_token(config: dict[str, Any]) -> str:
    token_cmd = str(config.get("token_cmd") or DEFAULT_TOKEN_CMD)
    return subprocess.check_output([token_cmd, "coding"], text=True).strip()


def authenticated_url(url: str, token: str) -> str:
    if not url.startswith("https://github.com/"):
        return url
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse(parsed._replace(netloc=f"x-access-token:{token}@{parsed.netloc}"))


def github_request(method: str, url: str, token: str, payload: Any | None = None) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        method=method,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "trading-coding-agent-mvp0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode()
        return json.loads(body) if body else None


def fetch_issue(config: dict[str, Any], issue: int, token: str) -> dict[str, Any]:
    owner, repo = repo_parts(config)
    return github_request("GET", f"https://api.github.com/repos/{owner}/{repo}/issues/{issue}", token)


def fetch_pr(config: dict[str, Any], pr_number: int, token: str) -> dict[str, Any]:
    owner, repo = repo_parts(config)
    return github_request("GET", f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}", token)


def fetch_pr_review_context(config: dict[str, Any], pr_number: int, token: str) -> dict[str, Any]:
    owner, repo = repo_parts(config)
    comments = github_request("GET", f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments?per_page=50", token)
    check_runs = github_request("GET", f"https://api.github.com/repos/{owner}/{repo}/commits/" + fetch_pr(config, pr_number, token)["head"]["sha"] + "/check-runs?per_page=50", token)
    return {"comments": comments, "check_runs": check_runs.get("check_runs", [])}


def label_names(item: dict[str, Any] | None) -> set[str]:
    labels = (item or {}).get("labels") or []
    names: set[str] = set()
    for label in labels:
        if isinstance(label, dict):
            name = label.get("name")
        else:
            name = str(label)
        if name:
            names.add(str(name))
    return names


def validate_fix_pr(config: dict[str, Any], fix_pr: dict[str, Any], pr_issue: dict[str, Any] | None = None) -> str:
    """Return a trusted PR branch or raise before fix mode can checkout/push it."""
    repo = str(config["repo"])
    base_branch = str(config.get("base_branch") or "main")
    head = fix_pr.get("head") or {}
    base = fix_pr.get("base") or {}
    branch = str(head.get("ref") or "")
    labels = label_names(pr_issue or fix_pr)
    failures: list[str] = []
    if not branch.startswith("agent/issue-"):
        failures.append("untrusted_branch")
    if (head.get("repo") or {}).get("full_name") != repo:
        failures.append("head_repo_mismatch")
    if (base.get("repo") or {}).get("full_name") != repo:
        failures.append("base_repo_mismatch")
    if base.get("ref") != base_branch:
        failures.append("base_branch_mismatch")
    if "agent:pr-opened" not in labels:
        failures.append("missing_agent_pr_opened_label")
    if "agent:blocked" in labels or "human:rejected" in labels:
        failures.append("blocked_or_rejected")
    if failures:
        raise RuntimeError(json.dumps({"refusing_untrusted_fix_pr": failures, "pr": fix_pr.get("number"), "branch": branch}, sort_keys=True))
    return branch


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return (slug[:max_len].strip("-") or "work")


def redact_text(text: str) -> str:
    text = re.sub(r"x-access-token:[^@\s]+@", "x-access-token:***@", text)
    text = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", "<private-key-redacted>", text, flags=re.S)
    text = re.sub(r"(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*[^\s]+", r"\1=<redacted>", text)
    return text


def run_cmd(cmd: list[str], *, cwd: Path | None = None, timeout: int = 180, env: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as exc:
        return {
            "command": redact_command(cmd),
            "returncode": 124,
            "stdout": redact_text(exc.stdout or ""),
            "stderr": redact_text(exc.stderr or "") + "\nCommand timed out",
        }
    return {"command": redact_command(cmd), "returncode": proc.returncode, "stdout": redact_text(proc.stdout), "stderr": redact_text(proc.stderr)}


def require_ok(result: dict[str, Any]) -> dict[str, Any]:
    if result["returncode"] != 0:
        raise RuntimeError(json.dumps(result, sort_keys=True))
    return result


def redact_command(cmd: list[str]) -> list[str]:
    return [redact_text(part) for part in cmd]


def ensure_issue_workspace(issue: int, config: dict[str, Any], token: str) -> dict[str, Any]:
    workspace_root = Path(str(config["workspace_root"]))
    workspace = workspace_root / f"issue-{issue}"
    git_dir = workspace / ".git"
    clone_url = repo_clone_url(config)
    auth_url = authenticated_url(clone_url, token)
    base_branch = str(config.get("base_branch") or "main")
    if git_dir.exists():
        require_ok(run_cmd(["git", "fetch", auth_url, base_branch], cwd=workspace, timeout=180))
        require_ok(run_cmd(["git", "checkout", base_branch], cwd=workspace))
        require_ok(run_cmd(["git", "reset", "--hard", "FETCH_HEAD"], cwd=workspace))
        require_ok(run_cmd(["git", "remote", "set-url", "origin", clone_url], cwd=workspace))
        checkout = "existing"
        created = False
    else:
        if workspace.exists() and any(workspace.iterdir()):
            raise RuntimeError(f"workspace exists but is not a git checkout: {workspace}")
        workspace.parent.mkdir(parents=True, exist_ok=True)
        require_ok(run_cmd(["git", "clone", "--branch", base_branch, "--single-branch", auth_url, str(workspace)], timeout=180))
        require_ok(run_cmd(["git", "remote", "set-url", "origin", clone_url], cwd=workspace))
        checkout = "git-clone"
        created = True
    commit = subprocess.check_output(["git", "-C", str(workspace), "rev-parse", "--short", "HEAD"], text=True).strip()
    return {"workspace": str(workspace), "created": created, "checkout": checkout, "base_branch": base_branch, "commit": commit}


def create_branch(workspace: Path, issue: int, title: str, existing_branch: str | None = None) -> dict[str, Any]:
    branch = existing_branch or f"agent/issue-{issue}-{slugify(title)}"
    require_ok(run_cmd(["git", "checkout", "-B", branch], cwd=workspace))
    return {"branch": branch}


def checkout_existing_pr_branch(workspace: Path, config: dict[str, Any], token: str, branch: str) -> None:
    auth_url = authenticated_url(repo_clone_url(config), token)
    require_ok(run_cmd(["git", "fetch", auth_url, f"+refs/heads/{branch}:refs/remotes/origin/{branch}"], cwd=workspace, timeout=180))
    require_ok(run_cmd(["git", "checkout", "-B", branch, f"refs/remotes/origin/{branch}"], cwd=workspace))


def build_prompt(issue: dict[str, Any], fix_context: dict[str, Any] | None = None) -> str:
    title = issue.get("title") or ""
    body = issue.get("body") or ""
    prompt = f"""
You are the MVP-0 Coding Agent working in a disposable git workspace.

Issue #{issue.get('number')}: {title}

Issue body:
{body[:4000]}

Task:
- Make one safe, minimal documentation-only change that addresses or records this issue.
- Prefer updating options-trade-lab/PROJECT_PLAN.md, options-trade-lab/README.md, or README.md.
- Do not touch secrets, credentials, deployment files, or generated caches.
- Keep the diff small.
- Run a minimal verification command if appropriate.
""".strip()
    if fix_context:
        comments = "\n\n".join((c.get("body") or "")[:1500] for c in fix_context.get("comments", [])[-5:])
        checks = "\n".join(f"{c.get('name')}: {c.get('conclusion')} - {(c.get('output') or {}).get('summary','')[:1000]}" for c in fix_context.get("check_runs", [])[-10:])
        prompt += f"\n\nFix mode context:\nRecent review comments:\n{comments}\n\nRecent check runs:\n{checks}\n\nUpdate the existing PR branch only."
    return prompt


def run_codex(workspace: Path, issue: dict[str, Any], config: dict[str, Any], args: argparse.Namespace, fix_context: dict[str, Any] | None = None) -> dict[str, Any]:
    prompt = build_prompt(issue, fix_context)
    logs_dir = Path(args.log_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = now_iso().replace(":", "")
    last_message = logs_dir / f"codex-issue-{issue['number']}-{ts}.txt"
    if args.skip_codex:
        # Deterministic fallback for local smoke tests; production runs should not use this.
        target = workspace / "options-trade-lab" / "PROJECT_PLAN.md"
        with target.open("a", encoding="utf-8") as f:
            f.write(f"\n<!-- coding-agent smoke issue #{issue['number']} at {now_iso()} -->\n")
        return {"skipped": True, "last_message": str(last_message), "returncode": 0, "stdout": "", "stderr": ""}
    cmd = [
        "codex",
        "exec",
        "--sandbox",
        "workspace-write",
        "-c",
        'approval_policy="never"',
        "-C",
        str(workspace),
        "--output-last-message",
        str(last_message),
        prompt,
    ]
    model = config.get("codex_model")
    if model:
        cmd[2:2] = ["--model", str(model)]
    result = run_cmd(cmd, cwd=workspace, timeout=args.codex_timeout_seconds)
    result["command"] = redact_command(cmd[:-1] + ["<coding-prompt-redacted>"])
    result["stdout"] = "<codex-stdout-redacted>"
    result["stderr"] = redact_text(result.get("stderr", ""))
    return result


def changed_files(workspace: Path) -> list[str]:
    out = subprocess.check_output(["git", "-C", str(workspace), "status", "--porcelain=v1", "-z"], text=True)
    entries = [entry for entry in out.split("\0") if entry]
    files: list[str] = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        status = entry[:2]
        path = entry[3:]
        if status[0] in {"R", "C"} or status[1] in {"R", "C"}:
            files.append(path)
            if i + 1 < len(entries):
                files.append(entries[i + 1])
            i += 2  # porcelain -z stores the old path in the following entry.
        else:
            files.append(path)
            i += 1
    return files


def verify(workspace: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    agent_file = workspace / "tools" / "trading_coding_agent.py"
    if agent_file.exists():
        checks.append(run_cmd(["python3", "-m", "py_compile", "agent-platform/tools/trading_coding_agent.py"], cwd=workspace, timeout=60))
    else:
        checks.append(run_cmd(["git", "diff", "--check"], cwd=workspace, timeout=30))
    return {"checks": checks, "ok": all(c["returncode"] == 0 for c in checks)}


def is_allowed_mvp0_change(path: str) -> bool:
    allowed_exact = {
        "README.md",
        "options-trade-lab/README.md",
        "options-trade-lab/PROJECT_PLAN.md",
        "options-trade-lab/ARCHITECTURE.md",
    }
    return path in allowed_exact or (path.startswith("options-trade-lab/docs/") and path.endswith(".md"))


def commit_changes(workspace: Path, issue: int, title: str) -> dict[str, Any]:
    files = changed_files(workspace)
    if not files:
        return {"committed": False, "reason": "no_changes", "files": []}
    disallowed = [path for path in files if not is_allowed_mvp0_change(path)]
    if disallowed:
        raise RuntimeError(json.dumps({"refusing_disallowed_mvp0_changes": disallowed}, sort_keys=True))
    require_ok(run_cmd(["git", "config", "user.name", "trading-coding-agent[bot]"], cwd=workspace))
    require_ok(run_cmd(["git", "config", "user.email", "trading-coding-agent[bot]@users.noreply.github.com"], cwd=workspace))
    require_ok(run_cmd(["git", "add", "--"] + files, cwd=workspace))
    msg = f"docs: address issue #{issue}"
    require_ok(run_cmd(["git", "commit", "-m", msg, "-m", title], cwd=workspace))
    sha = subprocess.check_output(["git", "-C", str(workspace), "rev-parse", "--short", "HEAD"], text=True).strip()
    return {"committed": True, "commit": sha, "files": files, "message": msg}


def push_branch(workspace: Path, config: dict[str, Any], token: str, branch: str) -> dict[str, Any]:
    if branch == str(config.get("base_branch") or "main"):
        raise RuntimeError("refusing to push base branch")
    auth_url = authenticated_url(repo_clone_url(config), token)
    # Populate remote-tracking ref when the branch already exists so --force-with-lease
    # can protect against clobbering unseen remote work.
    fetch_ref = f"refs/heads/{branch}:refs/remotes/origin/{branch}"
    fetch_result = run_cmd(["git", "fetch", auth_url, fetch_ref], cwd=workspace, timeout=180)
    if fetch_result["returncode"] not in {0, 128}:
        raise RuntimeError(json.dumps(fetch_result, sort_keys=True))
    expected = None
    rev = run_cmd(["git", "rev-parse", "--verify", f"refs/remotes/origin/{branch}"], cwd=workspace, timeout=30)
    if rev["returncode"] == 0:
        expected = rev["stdout"].strip()
    lease = f"--force-with-lease=refs/heads/{branch}:{expected}" if expected else "--force-with-lease"
    result = require_ok(run_cmd(["git", "push", auth_url, f"HEAD:refs/heads/{branch}", lease], cwd=workspace, timeout=180))
    return {"pushed": True, "branch": branch, "fetch": fetch_result, "expected": expected, "result": result}


def find_existing_pr(config: dict[str, Any], token: str, branch: str) -> dict[str, Any] | None:
    owner, repo = repo_parts(config)
    query = urllib.parse.urlencode({"state": "open", "head": f"{owner}:{branch}"})
    prs = github_request("GET", f"https://api.github.com/repos/{owner}/{repo}/pulls?{query}", token)
    return prs[0] if prs else None


def create_pr(config: dict[str, Any], token: str, issue: dict[str, Any], branch: str, verification: dict[str, Any]) -> dict[str, Any]:
    existing = find_existing_pr(config, token, branch)
    if existing:
        return {"created": False, "number": existing["number"], "url": existing["html_url"]}
    owner, repo = repo_parts(config)
    title = f"docs: address issue #{issue['number']}"
    body = (
        f"Addresses #{issue['number']}.\n\n"
        f"Summary:\n- MVP-0 Coding Agent produced a minimal docs/code change for: {issue.get('title') or ''}\n\n"
        f"Verification:\n```json\n{json.dumps(verification, indent=2, sort_keys=True)[:3000]}\n```\n"
    )
    pr = github_request(
        "POST",
        f"https://api.github.com/repos/{owner}/{repo}/pulls",
        token,
        {"title": title, "head": branch, "base": str(config.get("base_branch") or "main"), "body": body},
    )
    return {"created": True, "number": pr["number"], "url": pr["html_url"]}


def write_log(log_dir: Path, event: dict[str, Any]) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "coding-agent.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")
    log_path.chmod(0o600)
    return log_path


def cmd_run(args: argparse.Namespace) -> int:
    config, config_found = load_config(args.config)
    ts = now_iso()
    token = mint_token(config)
    issue = fetch_issue(config, args.issue, token)
    workspace_info = ensure_issue_workspace(args.issue, config, token)
    workspace = Path(workspace_info["workspace"])
    fix_pr = fetch_pr(config, args.fix_pr, token) if args.fix_pr else None
    fix_issue = fetch_issue(config, args.fix_pr, token) if args.fix_pr else None
    fix_context = fetch_pr_review_context(config, args.fix_pr, token) if args.fix_pr else None
    existing_branch = validate_fix_pr(config, fix_pr, fix_issue) if fix_pr else None
    if existing_branch:
        checkout_existing_pr_branch(workspace, config, token, existing_branch)
        branch_info = {"branch": existing_branch, "mode": "fix-pr"}
    else:
        branch_info = create_branch(workspace, args.issue, issue.get("title") or "work")
    codex_result = run_codex(workspace, issue, config, args, fix_context)
    if codex_result.get("returncode", 0) != 0:
        raise RuntimeError(json.dumps(codex_result, sort_keys=True))
    verification = verify(workspace)
    if not verification["ok"]:
        raise RuntimeError(json.dumps({"verification_failed": verification}, sort_keys=True))
    commit = commit_changes(workspace, args.issue, issue.get("title") or "")
    push = None
    pr = None
    if commit.get("committed"):
        push = push_branch(workspace, config, token, branch_info["branch"])
        pr = create_pr(config, token, issue, branch_info["branch"], verification)
    event = {
        "ok": True,
        "type": "coding_agent_run",
        "timestamp": ts,
        "issue": args.issue,
        "fix_pr": args.fix_pr,
        "config_path": str(args.config),
        "config_found": config_found,
        "workspace": workspace_info,
        "branch": branch_info,
        "codex": codex_result,
        "verification": verification,
        "commit": commit,
        "push": push,
        "pr": pr,
        "user": os.environ.get("USER") or os.environ.get("LOGNAME"),
    }
    log_path = write_log(args.log_dir, event)
    print(json.dumps({**event, "log_path": str(log_path)}, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trading-coding-agent")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run")
    run.add_argument("--issue", required=True, type=int)
    run.add_argument("--fix-pr", type=int)
    run.add_argument("--skip-codex", action="store_true", help="test-only deterministic workspace modification")
    run.add_argument("--codex-timeout-seconds", type=int, default=900)
    run.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
