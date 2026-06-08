#!/usr/bin/env python3
"""MVP-0 Coding Agent CLI skeleton.

This entry point intentionally does not modify repositories yet. It proves that
agent-coding can load configuration, accept an issue number, write an audit log,
and exit cleanly.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.parse
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


def repo_clone_url(config: dict[str, Any]) -> str:
    if config.get("repo_url"):
        return str(config["repo_url"])
    return f"https://github.com/{config['repo']}.git"


def authenticated_clone_url(clone_url: str, config: dict[str, Any]) -> str:
    if not clone_url.startswith("https://github.com/"):
        return clone_url
    token_cmd = str(config.get("token_cmd") or DEFAULT_TOKEN_CMD)
    token = subprocess.check_output([token_cmd, "coding"], text=True).strip()
    parsed = urllib.parse.urlparse(clone_url)
    return urllib.parse.urlunparse(parsed._replace(netloc=f"x-access-token:{token}@{parsed.netloc}"))


def ensure_issue_workspace(issue: int, config: dict[str, Any]) -> dict[str, Any]:
    workspace_root = Path(str(config["workspace_root"]))
    workspace = workspace_root / f"issue-{issue}"
    git_dir = workspace / ".git"
    if git_dir.exists():
        return {"workspace": str(workspace), "created": False, "checkout": "existing"}
    if workspace.exists() and any(workspace.iterdir()):
        raise RuntimeError(f"workspace exists but is not a git checkout: {workspace}")
    workspace.parent.mkdir(parents=True, exist_ok=True)
    clone_url = repo_clone_url(config)
    effective_clone_url = authenticated_clone_url(clone_url, config)
    base_branch = str(config.get("base_branch") or "main")
    subprocess.run(
        ["git", "clone", "--branch", base_branch, "--single-branch", effective_clone_url, str(workspace)],
        text=True,
        capture_output=True,
        check=True,
        timeout=180,
    )
    # Avoid leaving short-lived credentials in .git/config after HTTPS clone.
    subprocess.run(["git", "-C", str(workspace), "remote", "set-url", "origin", clone_url], check=True, timeout=30)
    commit = subprocess.check_output(["git", "-C", str(workspace), "rev-parse", "--short", "HEAD"], text=True).strip()
    return {"workspace": str(workspace), "created": True, "checkout": "git-clone", "base_branch": base_branch, "commit": commit}


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
    workspace = ensure_issue_workspace(args.issue, config)
    event = {
        "ok": True,
        "type": "coding_agent_run",
        "timestamp": ts,
        "issue": args.issue,
        "config_path": str(args.config),
        "config_found": config_found,
        "config": config,
        "workspace": workspace,
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
    run.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
