#!/usr/bin/env python3
"""MVP-0 Review Agent CLI.

Creates an isolated PR review workspace, fetches PR metadata/diff, runs a
standard checklist analysis, writes review.md, and publishes the stable required
GitHub check `review-agent/pass` plus a PR comment.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import yaml

DEFAULT_CONFIG_PATH = Path(os.environ.get("TRADING_REVIEW_CONFIG", "/agents/review/config.json"))
DEFAULT_LOG_DIR = Path(os.environ.get("TRADING_REVIEW_LOG_DIR", "/agents/review/logs"))
DEFAULT_TOKEN_CMD = os.environ.get("TRADING_AGENT_TOKEN_CMD", "trading-agent-token")
CHECK_NAME = "review-agent/pass"
MAX_WORKFLOW_YAML_BYTES = 1_000_000

DEFAULT_CONFIG: dict[str, Any] = {
    "agent": "review",
    "repo": "atzmonpersonalassistant/trader",
    "base_branch": "main",
    "workspace_root": "/agents/review/workspaces",
    "token_cmd": DEFAULT_TOKEN_CMD,
    "review_model": "gpt-5.5",
    "autoreview_enabled": False,
    "autoreview_cmd": "autoreview",
    "autoreview_timeout_seconds": 1800,
    "autoreview_required": False,
    "autoreview_max_changed_files": 12,
}

CHECKLIST = [
    "code quality",
    "test coverage or reasonable explanation",
    "no secrets",
    "no live trading changes without approval",
    "no risk/secrets/auth changes without approval",
    "no obviously unsafe behavior",
    "issue requirements addressed",
]


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


def mint_token(config: dict[str, Any]) -> str:
    return subprocess.check_output([str(config.get("token_cmd") or DEFAULT_TOKEN_CMD), "review"], text=True).strip()


def github_request(method: str, url: str, token: str, payload: Any | None = None, accept: str = "application/vnd.github+json") -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        method=method,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": accept,
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "trading-review-agent-mvp0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode()
        if accept == "application/vnd.github.v3.diff":
            return body
        return json.loads(body) if body else None


def repo_clone_url(config: dict[str, Any]) -> str:
    if config.get("repo_url"):
        return str(config["repo_url"])
    return f"https://github.com/{config['repo']}.git"


def authenticated_url(url: str, token: str) -> str:
    if not url.startswith("https://github.com/"):
        return url
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse(parsed._replace(netloc=f"x-access-token:{token}@{parsed.netloc}"))


def redact_text(text: str) -> str:
    text = re.sub(r"x-access-token:[^@\s]+@", "x-access-token:***@", text)
    text = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", "<private-key-redacted>", text, flags=re.S)
    text = re.sub(r"(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*[^\s`'\"]+", r"\1=<redacted>", text)
    text = re.sub(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b", "<github-token-redacted>", text)
    text = re.sub(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", "<github-token-redacted>", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{20,}\b", "<openai-token-redacted>", text)
    return text


def run_cmd(cmd: list[str], *, cwd: Path | None = None, timeout: int = 180, input_text: str | None = None) -> dict[str, Any]:
    redacted = [redact_text(part) for part in cmd]
    try:
        proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout, input=input_text)
    except subprocess.TimeoutExpired as exc:
        return {
            "command": redacted,
            "returncode": 124,
            "stdout": redact_text(exc.stdout or ""),
            "stderr": redact_text(exc.stderr or "") + "\nCommand timed out",
        }
    return {"command": redacted, "returncode": proc.returncode, "stdout": redact_text(proc.stdout), "stderr": redact_text(proc.stderr)}


def require_ok(result: dict[str, Any]) -> dict[str, Any]:
    if result["returncode"] != 0:
        raise RuntimeError(json.dumps(result, sort_keys=True))
    return result


def fetch_pr_context(config: dict[str, Any], pr_number: int, token: str) -> dict[str, Any]:
    owner, repo = repo_parts(config)
    pr = github_request("GET", f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}", token)
    issue = github_request("GET", f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}", token)
    pr["labels"] = issue.get("labels", [])
    files: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = github_request("GET", f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files?per_page=100&page={page}", token)
        files.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    diff = github_request("GET", f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}", token, accept="application/vnd.github.v3.diff")
    linked_issue = None
    for text in [pr.get("body") or "", pr.get("title") or ""]:
        import re
        m = re.search(r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|addresses)\s+#(\d+)|#(\d+)", text, flags=re.I)
        if m:
            issue_number = int(m.group(1) or m.group(2))
            linked_issue = github_request("GET", f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}", token)
            break
    return {"pr": pr, "files": files, "diff": diff, "linked_issue": linked_issue}


def ensure_review_workspace(config: dict[str, Any], pr_number: int, token: str, context: dict[str, Any]) -> dict[str, Any]:
    workspace = Path(str(config["workspace_root"])) / f"pr-{pr_number}"
    auth_url = authenticated_url(repo_clone_url(config), token)
    clean_url = repo_clone_url(config)
    head_ref = context["pr"]["head"]["ref"]
    base_ref = context["pr"]["base"]["ref"]
    if not (workspace / ".git").exists():
        workspace.parent.mkdir(parents=True, exist_ok=True)
        require_ok(run_cmd(["git", "clone", auth_url, str(workspace)], timeout=180))
        require_ok(run_cmd(["git", "remote", "set-url", "origin", clean_url], cwd=workspace))
    require_ok(
        run_cmd(
            [
                "git",
                "fetch",
                auth_url,
                f"refs/heads/{base_ref}:refs/remotes/origin/{base_ref}",
                f"refs/heads/{head_ref}:refs/remotes/origin/{head_ref}",
            ],
            cwd=workspace,
            timeout=180,
        )
    )
    require_ok(run_cmd(["git", "checkout", "-B", f"review/pr-{pr_number}", f"refs/remotes/origin/{head_ref}"], cwd=workspace))
    artifacts = workspace / ".review-agent"
    artifacts.mkdir(exist_ok=True)
    safe_context_json = json.dumps({k: v for k, v in context.items() if k != "diff"}, indent=2, sort_keys=True)
    (artifacts / "context.json").write_text(redact_text(safe_context_json), encoding="utf-8")
    (artifacts / "diff.patch").write_text(redact_text(context["diff"]), encoding="utf-8")
    return {"workspace": str(workspace), "head_ref": head_ref, "base_ref": base_ref, "artifacts": str(artifacts)}


def added_diff_lines(diff: str) -> list[str]:
    return [line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]


def has_secret_like_text(diff: str) -> bool:
    added_text = "\n".join(added_diff_lines(diff))
    if re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", added_text):
        return True
    token_patterns = [
        r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b",
        r"\bgithub_pat_[A-Za-z0-9_]{20,}\b",
        r"\bsk-[A-Za-z0-9_-]{20,}\b",
    ]
    if any(re.search(pattern, added_text) for pattern in token_patterns):
        return True
    assignment = re.compile(r"(?i)^\s*([A-Z0-9_]*(?:API[_-]?KEY|PASSWORD|SECRET|TOKEN)[A-Z0-9_]*)\s*[:=]\s*['\"]?([^\s'\"]{8,})")
    for line in added_diff_lines(diff):
        match = assignment.search(line)
        if not match:
            continue
        value = match.group(2)
        if value.startswith("${{") or value.startswith("<") or value.startswith("***") or "(" in value:
            continue
        if value.startswith(("os.environ", "str(", "dict(", "json.", "urllib.", "subprocess.", "Path(", "mint_github_token(")):
            continue
        return True
    return False


def deterministic_review(context: dict[str, Any]) -> dict[str, Any]:
    diff = context["diff"]
    lower = diff.lower()
    findings: list[str] = []
    if has_secret_like_text(diff):
        findings.append("Potential secret-like text found in diff.")
    if any(term in lower for term in ["live trading", "ibkr", "position sizing", "risk limit"]):
        labels = [label.get("name") for label in context["pr"].get("labels", [])]
        if "human:approved" not in labels:
            findings.append("Potential trading/risk-sensitive change lacks human:approved label.")
    passed = not findings
    return {"pass": passed, "findings": findings, "checklist": CHECKLIST}


def local_validation_findings(workspace: Path, context: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    workspace_root = workspace.resolve()
    for item in context.get("files", []):
        filename = str(item.get("filename") or "")
        if not filename.startswith(".github/workflows/") or not filename.endswith((".yml", ".yaml")):
            continue
        path = workspace / filename
        try:
            relative_path = path.relative_to(workspace)
        except ValueError:
            findings.append(f"Workflow path is outside review workspace: {filename}")
            continue
        if ".." in relative_path.parts:
            findings.append(f"Workflow path escapes review workspace: {filename}")
            continue
        if path.is_symlink():
            findings.append(f"Workflow YAML must be a regular file, not a symlink: {filename}")
            continue
        try:
            resolved = path.resolve(strict=False)
            resolved.relative_to(workspace_root)
        except ValueError:
            findings.append(f"Workflow path resolves outside review workspace: {filename}")
            continue
        if not path.exists():
            continue
        stat = path.stat()
        if not path.is_file():
            findings.append(f"Workflow YAML must be a regular file: {filename}")
            continue
        if stat.st_size > MAX_WORKFLOW_YAML_BYTES:
            findings.append(f"Workflow YAML is too large to parse safely: {filename}: {stat.st_size} bytes")
            continue
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            findings.append(f"Workflow YAML does not parse: {filename}: {exc}")
    return findings


def run_model_review(workspace: Path, context: dict[str, Any], config: dict[str, Any], timeout: int) -> dict[str, Any]:
    prompt = (
        "Review this PR using the checklist below. Return concise Markdown with PASS or FAIL first.\n\n"
        + "Checklist:\n"
        + "\n".join(f"- {item}" for item in CHECKLIST)
        + "\n\nPR title: " + (context["pr"].get("title") or "")
        + "\nPR labels: " + ", ".join(label.get("name", "") for label in context["pr"].get("labels", []))
        + "\nPR body:\n" + (context["pr"].get("body") or "")[:3000]
        + "\nChanged files:\n" + "\n".join(f.get("filename", "") for f in context["files"])
        + "\nDiff:\n" + context["diff"]
    )
    output = workspace / ".review-agent" / "model-review.md"
    cmd = [
        "codex", "exec", "--skip-git-repo-check", "--model", str(config.get("review_model") or "gpt-5.5"),
        "--sandbox", "workspace-write", "-c", 'approval_policy="never"',
        "-C", str(workspace), "--output-last-message", str(output),
    ]
    result = run_cmd(cmd, cwd=workspace, timeout=timeout, input_text=prompt)
    # Do not persist the full review prompt/diff in JSON logs. The prompt can
    # contain PR content, including the very secrets this agent is meant to flag.
    result["command"] = cmd[:-1] + ["<review-prompt-redacted>"]
    result["stdout"] = "<codex-stdout-redacted>"
    result["stderr"] = "<codex-stderr-redacted>"
    if result["returncode"] == 0 and output.exists():
        result["review_text"] = redact_text(output.read_text(encoding="utf-8"))
    return result


def should_run_autoreview(context: dict[str, Any], config: dict[str, Any], deterministic: dict[str, Any], model: dict[str, Any] | None, skip_autoreview: bool) -> bool:
    if skip_autoreview or not config.get("autoreview_enabled"):
        return False
    if not deterministic.get("pass"):
        return False
    if not model or model.get("returncode") != 0 or not str(model.get("review_text") or "").strip().upper().startswith("PASS"):
        return False
    files = [f.get("filename", "") for f in context.get("files", [])]
    labels = {label.get("name") for label in context.get("pr", {}).get("labels", [])}
    if len(files) > int(config.get("autoreview_max_changed_files") or 12):
        return True
    sensitive_terms = ("auth", "secret", "deploy", "workflow", "risk", "trading", "ibkr", "orchestrator", "coding_agent", "review_agent")
    if any(any(term in filename.lower() for term in sensitive_terms) for filename in files):
        return True
    if "needs:human-approval" in labels or "human:approved" in labels:
        return True
    return False


def run_autoreview(workspace: Path, workspace_info: dict[str, Any], config: dict[str, Any], timeout: int) -> dict[str, Any]:
    base_ref = workspace_info.get("base_ref") or config.get("base_branch") or "main"
    cmd = [str(config.get("autoreview_cmd") or "autoreview"), "--mode", "branch", "--base", f"origin/{base_ref}"]
    result = run_cmd(cmd, cwd=workspace, timeout=timeout)
    # Keep logs bounded; autoreview can be verbose.
    result["stdout"] = redact_text(str(result.get("stdout") or ""))[:12000]
    result["stderr"] = redact_text(str(result.get("stderr") or ""))[:6000]
    return result


def deterministic_secret_blocked(deterministic: dict[str, Any]) -> bool:
    return any("secret" in str(finding).lower() for finding in deterministic.get("findings") or [])


def should_run_model_review(deterministic: dict[str, Any], skip_model: bool) -> bool:
    if skip_model:
        return False
    # If deterministic checks already found secret-like content, fail closed
    # before sending any PR diff to an external/model review process.
    return not deterministic_secret_blocked(deterministic)


def write_review(workspace: Path, pr_number: int, deterministic: dict[str, Any], model: dict[str, Any] | None, autoreview: dict[str, Any] | None = None, autoreview_required: bool = False) -> tuple[Path, str, bool]:
    passed = bool(deterministic["pass"])
    model_findings: list[str] = []
    if not model:
        passed = False
        if deterministic_secret_blocked(deterministic):
            model_findings.append("Model review skipped because deterministic secret checks failed; raw diff was not sent to the model.")
        else:
            model_findings.append("Model review was skipped; required check cannot pass.")
    elif model.get("returncode") != 0 or not model.get("review_text"):
        passed = False
        model_findings.append("Model review failed or returned no review text; required check cannot pass.")
    else:
        text = redact_text(model["review_text"])
        model["review_text"] = text
        normalized = text.strip().upper()
        if normalized.startswith("FAIL"):
            passed = False
        elif normalized.startswith("PASS") and passed:
            passed = True
        else:
            passed = False
            model_findings.append("Model review did not start with PASS or FAIL; required check cannot pass.")
    autoreview_body: list[str] = []
    if autoreview:
        if autoreview.get("skipped"):
            autoreview_body.extend(["", "## Autoreview", "Skipped: " + str(autoreview.get("reason") or "not required")])
        elif autoreview.get("returncode") == 0:
            autoreview_body.extend(["", "## Autoreview", "PASS", str(autoreview.get("stdout") or "")[:3000]])
        else:
            if autoreview_required:
                passed = False
            autoreview_body.extend(["", "## Autoreview", "FAIL" if autoreview_required else "Non-blocking failure", str(autoreview.get("stdout") or "")[:3000], str(autoreview.get("stderr") or "")[:3000]])
    body = [f"# Review Agent result for PR #{pr_number}", "", f"Result: {'PASS' if passed else 'FAIL'}", "", "## Checklist"]
    body.extend(f"- {item}" for item in CHECKLIST)
    body.append("\n## Findings")
    findings = list(deterministic["findings"] or []) + model_findings
    body.extend(f"- {f}" for f in findings or ["No blocking findings."])
    body.extend(autoreview_body)
    if model and model.get("review_text"):
        body.extend(["", "## Model review", model["review_text"][:6000]])
    review_path = workspace / ".review-agent" / "review.md"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_text = "\n".join(body) + "\n"
    review_path.write_text(review_text, encoding="utf-8")
    return review_path, review_text, passed


def publish(config: dict[str, Any], token: str, context: dict[str, Any], review_text: str, passed: bool) -> dict[str, Any]:
    owner, repo = repo_parts(config)
    pr = context["pr"]
    conclusion = "success" if passed else "failure"
    check = github_request("POST", f"https://api.github.com/repos/{owner}/{repo}/check-runs", token, {
        "name": CHECK_NAME,
        "head_sha": pr["head"]["sha"],
        "status": "completed",
        "conclusion": conclusion,
        "output": {"title": f"Review Agent {'PASS' if passed else 'FAIL'}", "summary": review_text[:65000]},
    })
    comment = github_request("POST", f"https://api.github.com/repos/{owner}/{repo}/issues/{pr['number']}/comments", token, {"body": review_text[:65000]})
    return {"check_run_id": check["id"], "check_url": check.get("html_url"), "comment_id": comment["id"], "conclusion": conclusion}


def write_log(log_dir: Path, event: dict[str, Any]) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "review-agent.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")
    path.chmod(0o600)
    return path


def cmd_review(args: argparse.Namespace) -> int:
    config, config_found = load_config(args.config)
    token = mint_token(config)
    context = fetch_pr_context(config, args.pr, token)
    workspace_info = ensure_review_workspace(config, args.pr, token, context)
    workspace = Path(workspace_info["workspace"])
    deterministic = deterministic_review(context)
    local_findings = local_validation_findings(workspace, context)
    if local_findings:
        deterministic["pass"] = False
        deterministic["findings"] = list(deterministic.get("findings") or []) + local_findings
    model = run_model_review(workspace, context, config, args.model_timeout_seconds) if should_run_model_review(deterministic, args.skip_model) else None
    autoreview: dict[str, Any] | None
    if should_run_autoreview(context, config, deterministic, model, args.skip_autoreview):
        autoreview_timeout = args.autoreview_timeout_seconds if args.autoreview_timeout_seconds is not None else int(config.get("autoreview_timeout_seconds") or 1800)
        autoreview = run_autoreview(workspace, workspace_info, config, autoreview_timeout)
    else:
        autoreview = {"skipped": True, "reason": "not_required_or_disabled"}
    review_path, review_text, passed = write_review(workspace, args.pr, deterministic, model, autoreview, bool(config.get("autoreview_required")))
    published = publish(config, token, context, review_text, passed)
    event = {"ok": True, "type": "review_agent_review", "pr": args.pr, "config_found": config_found, "workspace": workspace_info, "review_path": str(review_path), "passed": passed, "deterministic": deterministic, "model": model, "autoreview": autoreview, "published": published, "user": os.environ.get("USER") or os.environ.get("LOGNAME"), "timestamp": now_iso()}
    log_path = write_log(args.log_dir, event)
    print(json.dumps({**event, "log_path": str(log_path)}, indent=2, sort_keys=True))
    return 0 if passed else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trading-review-agent")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("review")
    review.add_argument("--pr", required=True, type=int)
    review.add_argument("--skip-model", action="store_true")
    review.add_argument("--model-timeout-seconds", type=int, default=900)
    review.add_argument("--skip-autoreview", action="store_true")
    review.add_argument("--autoreview-timeout-seconds", type=int, default=None)
    review.set_defaults(func=cmd_review)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
