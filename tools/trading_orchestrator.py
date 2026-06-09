#!/usr/bin/env python3
"""MVP-0 trading orchestrator CLI skeleton.

This is intentionally small: it creates the durable SQLite schema, exposes
operator commands, and implements a safe SQLite backup command. GitHub polling
and agent dispatch are added in later Group D tasks.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(os.environ.get("TRADING_ORCHESTRATOR_DB", "/agents/orchestrator/state/orchestrator.db"))
DEFAULT_BACKUP_DIR = Path(os.environ.get("TRADING_ORCHESTRATOR_BACKUP_DIR", "/agents/orchestrator/backups"))
DEFAULT_GITHUB_OWNER = os.environ.get("TRADING_GITHUB_OWNER", "atzmonpersonalassistant")
DEFAULT_GITHUB_REPO = os.environ.get("TRADING_GITHUB_REPO", "trader")
DEFAULT_READY_LABEL = os.environ.get("TRADING_READY_LABEL", "agent:ready")
DEFAULT_CLAIMED_LABEL = os.environ.get("TRADING_CLAIMED_LABEL", "agent:claimed")
DEFAULT_TOKEN_CMD = os.environ.get("TRADING_AGENT_TOKEN_CMD", "trading-agent-token")
DEFAULT_CODING_STUB_CMD = os.environ.get("TRADING_CODING_STUB_CMD", "trading-coding-agent-stub")
DEFAULT_CODING_AGENT_CMD = os.environ.get("TRADING_CODING_AGENT_CMD", "trading-coding-agent")
DEFAULT_REVIEW_CHECK_NAME = os.environ.get("TRADING_REVIEW_CHECK_NAME", "review-agent/pass")
DEFAULT_REVIEW_APP_SLUG = os.environ.get("TRADING_REVIEW_APP_SLUG", "trading-review-agent")
DEFAULT_MAX_REVIEW_FIX_RETRIES = int(os.environ.get("TRADING_MAX_REVIEW_FIX_RETRIES", "50"))

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT NOT NULL UNIQUE,
  number INTEGER,
  title TEXT,
  state TEXT NOT NULL DEFAULT 'unknown',
  labels TEXT NOT NULL DEFAULT '[]',
  payload_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pull_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT NOT NULL UNIQUE,
  number INTEGER,
  issue_external_id TEXT,
  branch TEXT,
  state TEXT NOT NULL DEFAULT 'unknown',
  labels TEXT NOT NULL DEFAULT '[]',
  payload_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(issue_external_id) REFERENCES issues(external_id)
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT UNIQUE,
  entity_type TEXT NOT NULL,
  entity_external_id TEXT,
  event_type TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'new',
  payload_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS locks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL DEFAULT 'held',
  owner TEXT NOT NULL,
  labels TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  expires_at TEXT
);

CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT NOT NULL UNIQUE,
  entity_type TEXT NOT NULL,
  entity_external_id TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'started',
  labels TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  result_json TEXT
);

CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL DEFAULT 'pending',
  labels TEXT NOT NULL DEFAULT '[]',
  channel TEXT,
  message TEXT NOT NULL,
  payload_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS inbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL DEFAULT 'new',
  labels TEXT NOT NULL DEFAULT '[]',
  source TEXT,
  message TEXT NOT NULL,
  payload_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  acknowledged_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""

TABLES = ["issues", "pull_requests", "events", "locks", "attempts", "outbox", "inbox", "settings"]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def redact_text(text: str) -> str:
    text = re.sub(r"x-access-token:[^@\s]+@", "x-access-token:***@", text)
    text = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", "<private-key-redacted>", text, flags=re.S)
    return text


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        db_path.chmod(0o600)
    except FileNotFoundError:
        pass
    return conn


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        ts = now_iso()
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("schema_version", "1", ts, ts),
        )


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in TABLES}


def mint_github_token(token_cmd: str) -> str:
    return subprocess.check_output([token_cmd, "orchestrator"], text=True).strip()


def github_request(method: str, url: str, token: str, payload: Any | None = None) -> tuple[Any, dict[str, str]]:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        method=method,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "trading-orchestrator-mvp0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        headers = {k.lower(): v for k, v in resp.headers.items()}
        body = resp.read().decode()
        return (json.loads(body) if body else None), headers


def github_api_get(url: str, token: str) -> tuple[Any, dict[str, str]]:
    return github_request("GET", url, token)


def github_api_post(url: str, token: str, payload: Any) -> tuple[Any, dict[str, str]]:
    return github_request("POST", url, token, payload)


def github_api_delete(url: str, token: str) -> tuple[Any, dict[str, str]]:
    return github_request("DELETE", url, token)


def merge_pull_request(owner: str, repo: str, pr_number: int, token: str, head_sha: str) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/merge"
    data, _ = github_request("PUT", url, token, {"merge_method": "squash", "sha": head_sha})
    return data


def delete_branch_ref(owner: str, repo: str, branch: str, token: str) -> bool:
    encoded = urllib.parse.quote(f"heads/{branch}", safe="")
    try:
        github_api_delete(f"https://api.github.com/repos/{owner}/{repo}/git/refs/{encoded}", token)
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 422:
            return False
        raise


def github_graphql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    data, _ = github_request(
        "POST",
        "https://api.github.com/graphql",
        token,
        {"query": query, "variables": variables},
    )
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], sort_keys=True))
    return data["data"]


def fetch_issue_labels(owner: str, repo: str, number: int, token: str) -> list[str]:
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
    issue, _ = github_api_get(url, token)
    return [label.get("name") for label in issue.get("labels", []) if label.get("name")]


def parse_next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        section = part.strip()
        if 'rel="next"' not in section:
            continue
        start = section.find("<")
        end = section.find(">")
        if start != -1 and end != -1 and end > start:
            return section[start + 1 : end]
    return None


def fetch_ready_issues(owner: str, repo: str, label: str, token: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "state": "open",
            "labels": label,
            "per_page": "100",
            "sort": "created",
            "direction": "asc",
        }
    )
    url: str | None = f"https://api.github.com/repos/{owner}/{repo}/issues?{query}"
    issues: list[dict[str, Any]] = []
    while url:
        page, headers = github_api_get(url, token)
        # GitHub's issues endpoint includes PRs; exclude them.
        issues.extend(item for item in page if "pull_request" not in item)
        url = parse_next_link(headers.get("link"))
    return issues


def upsert_issue(conn: sqlite3.Connection, issue: dict[str, Any]) -> str:
    ts = now_iso()
    external_id = str(issue["id"])
    labels = [label.get("name") for label in issue.get("labels", []) if label.get("name")]
    existing = conn.execute("SELECT id FROM issues WHERE external_id=?", (external_id,)).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE issues
            SET number=?, title=?, state=?, labels=?, payload_json=?, updated_at=?, last_seen_at=?
            WHERE external_id=?
            """,
            (
                issue.get("number"),
                issue.get("title") or "",
                issue.get("state") or "unknown",
                json.dumps(labels, sort_keys=True),
                json.dumps(issue, sort_keys=True),
                ts,
                ts,
                external_id,
            ),
        )
        return "updated"
    conn.execute(
        """
        INSERT INTO issues(external_id, number, title, state, labels, payload_json, created_at, updated_at, last_seen_at, retry_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            external_id,
            issue.get("number"),
            issue.get("title") or "",
            issue.get("state") or "unknown",
            json.dumps(labels, sort_keys=True),
            json.dumps(issue, sort_keys=True),
            ts,
            ts,
            ts,
        ),
    )
    return "inserted"


def fetch_open_prs(owner: str, repo: str, token: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "state": "open",
            "per_page": "100",
            "sort": "created",
            "direction": "asc",
        }
    )
    url: str | None = f"https://api.github.com/repos/{owner}/{repo}/pulls?{query}"
    prs: list[dict[str, Any]] = []
    while url:
        page, headers = github_api_get(url, token)
        prs.extend(page)
        url = parse_next_link(headers.get("link"))
    return prs


def fetch_pr(owner: str, repo: str, pr_number: int, token: str) -> dict[str, Any]:
    pr, _ = github_api_get(f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}", token)
    return pr


def infer_issue_number_from_pr(pr: dict[str, Any]) -> int | None:
    text = "\n".join(
        str(value or "")
        for value in [
            pr.get("title"),
            pr.get("body"),
            (pr.get("head") or {}).get("ref"),
        ]
    )
    patterns = [
        r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)",
        r"issue[-_/ ]+(\d+)",
        r"#(\d+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def is_trusted_agent_pr(pr: dict[str, Any]) -> bool:
    branch = ((pr.get("head") or {}).get("ref")) or ""
    head_repo = (((pr.get("head") or {}).get("repo") or {}).get("full_name"))
    base_repo = (((pr.get("base") or {}).get("repo") or {}).get("full_name"))
    return branch.startswith("agent/issue-") and bool(head_repo) and head_repo == base_repo


def upsert_pr(conn: sqlite3.Connection, pr: dict[str, Any], issue_external_id: str | None) -> str:
    ts = now_iso()
    external_id = str(pr["id"])
    existing = conn.execute("SELECT id FROM pull_requests WHERE external_id=?", (external_id,)).fetchone()
    branch = ((pr.get("head") or {}).get("ref")) or ""
    if existing:
        conn.execute(
            """
            UPDATE pull_requests
            SET number=?, issue_external_id=?, branch=?, state=?, labels=?, payload_json=?, updated_at=?, last_seen_at=?
            WHERE external_id=?
            """,
            (
                pr.get("number"),
                issue_external_id,
                branch,
                pr.get("state") or "unknown",
                json.dumps(["agent:pr-opened"], sort_keys=True),
                json.dumps(pr, sort_keys=True),
                ts,
                ts,
                external_id,
            ),
        )
        return "updated"
    conn.execute(
        """
        INSERT INTO pull_requests(external_id, number, issue_external_id, branch, state, labels, payload_json, created_at, updated_at, last_seen_at, retry_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            external_id,
            pr.get("number"),
            issue_external_id,
            branch,
            pr.get("state") or "unknown",
            json.dumps(["agent:pr-opened"], sort_keys=True),
            json.dumps(pr, sort_keys=True),
            ts,
            ts,
            ts,
        ),
    )
    return "inserted"


def cmd_status(args: argparse.Namespace) -> int:
    init_db(args.db)
    with connect(args.db) as conn:
        data: dict[str, Any] = {
            "ok": True,
            "db_path": str(args.db),
            "backup_dir": str(args.backup_dir),
            "schema_version": conn.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()[0],
            "counts": table_counts(conn),
        }
    print(json.dumps(data, indent=2, sort_keys=True))
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    init_db(args.db)
    token = mint_github_token(args.token_cmd)
    ready_issues = fetch_ready_issues(args.owner, args.repo, args.ready_label, token)
    inserted = 0
    updated = 0
    with connect(args.db) as conn:
        for issue in ready_issues:
            action = upsert_issue(conn, issue)
            if action == "inserted":
                inserted += 1
            else:
                updated += 1
        next_row = conn.execute(
            """
            SELECT external_id, number, title, state, labels, retry_count, last_seen_at
            FROM issues
            WHERE state='open' AND labels LIKE ?
            ORDER BY number ASC
            LIMIT 1
            """,
            (f'%"{args.ready_label}"%',),
        ).fetchone()
    data = {
        "ok": True,
        "command": "scan",
        "implemented": True,
        "owner": args.owner,
        "repo": args.repo,
        "ready_label": args.ready_label,
        "found": len(ready_issues),
        "inserted": inserted,
        "updated": updated,
        "next_issue": dict(next_row) if next_row else None,
    }
    print(json.dumps(data, indent=2, sort_keys=True))
    return 0


def cmd_scan_prs(args: argparse.Namespace) -> int:
    init_db(args.db)
    token = mint_github_token(args.token_cmd)
    prs = fetch_open_prs(args.owner, args.repo, token)
    inserted = 0
    updated = 0
    matched = 0
    label_updates = 0
    label_update_errors: list[dict[str, Any]] = []
    pr_summaries: list[dict[str, Any]] = []
    with connect(args.db) as conn:
        for pr in prs:
            issue_external_id = None
            if not is_trusted_agent_pr(pr):
                continue
            pr_number = int(pr["number"])
            pr_labels_url = f"https://api.github.com/repos/{args.owner}/{args.repo}/issues/{pr_number}/labels"
            label_update_ok = True
            try:
                github_api_post(pr_labels_url, token, {"labels": ["agent:pr-opened"]})
                label_updates += 1
            except urllib.error.HTTPError as exc:
                label_update_ok = False
                # Some GitHub App contexts cannot mutate labels on certain PR resources.
                # Keep PR state durable in SQLite and report the external-label failure.
                if exc.code not in {403, 404}:
                    raise
                label_update_errors.append({"pr": pr_number, "status": exc.code, "reason": str(exc)})
            issue_number = infer_issue_number_from_pr(pr)
            if issue_number is not None:
                issue_row = conn.execute("SELECT external_id FROM issues WHERE number=?", (issue_number,)).fetchone()
                if issue_row:
                    issue_external_id = str(issue_row["external_id"])
                    matched += 1
            action = upsert_pr(conn, pr, issue_external_id)
            if action == "inserted":
                inserted += 1
            else:
                updated += 1
            pr_summaries.append(
                {
                    "number": pr_number,
                    "title": pr.get("title"),
                    "branch": ((pr.get("head") or {}).get("ref")) or "",
                    "issue_number": issue_number,
                    "issue_external_id": issue_external_id,
                    "github_label_updated": label_update_ok,
                }
            )
    print(
        json.dumps(
            {
                "ok": True,
                "command": "scan-prs",
                "implemented": True,
                "owner": args.owner,
                "repo": args.repo,
                "found": len(prs),
                "inserted": inserted,
                "updated": updated,
                "matched_to_issues": matched,
                "github_label_updates": label_updates,
                "github_label_update_errors": label_update_errors,
                "pull_requests": pr_summaries,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    init_db(args.db)
    token = mint_github_token(args.token_cmd)
    # Refresh before claiming so SQLite reflects current GitHub state.
    ready_issues = fetch_ready_issues(args.owner, args.repo, args.ready_label, token)
    with connect(args.db) as conn:
        for issue in ready_issues:
            upsert_issue(conn, issue)
        active_count = conn.execute(
            """
            SELECT COUNT(*) FROM issues
            WHERE state='open' AND (labels LIKE ? OR labels LIKE ?)
            """,
            (f'%"{args.claimed_label}"%', '%"agent:in-progress"%'),
        ).fetchone()[0]
        if active_count >= args.max_claimed:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "claimed": False,
                        "reason": "max_claimed_reached",
                        "active_count": active_count,
                        "max_claimed": args.max_claimed,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        row = conn.execute(
            """
            SELECT external_id, number, title, labels, retry_count
            FROM issues
            WHERE state='open'
              AND labels LIKE ?
              AND labels NOT LIKE ?
              AND labels NOT LIKE ?
              AND labels NOT LIKE ?
            ORDER BY number ASC
            LIMIT 1
            """,
            (
                f'%"{args.ready_label}"%',
                f'%"{args.claimed_label}"%',
                '%"agent:in-progress"%',
                '%"agent:blocked"%',
            ),
        ).fetchone()
        if not row:
            print(json.dumps({"ok": True, "claimed": False, "reason": "no_ready_issue"}, indent=2, sort_keys=True))
            return 0
        issue_number = int(row["number"])
        issue_url = f"https://api.github.com/repos/{args.owner}/{args.repo}/issues/{issue_number}"
        labels_url = f"{issue_url}/labels"
        github_api_post(labels_url, token, {"labels": [args.claimed_label]})
        if args.remove_ready_label:
            encoded_label = urllib.parse.quote(args.ready_label, safe="")
            try:
                github_api_delete(f"{labels_url}/{encoded_label}", token)
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
        refreshed, _ = github_api_get(issue_url, token)
        upsert_issue(conn, refreshed)
        ts = now_iso()
        lock_id = f"issue-{issue_number}"
        conn.execute(
            """
            INSERT INTO locks(external_id, state, owner, labels, created_at, updated_at, last_seen_at, retry_count)
            VALUES (?, 'held', 'agent-orchestrator', ?, ?, ?, ?, 0)
            ON CONFLICT(external_id) DO UPDATE SET
              state='held', owner='agent-orchestrator', labels=excluded.labels,
              updated_at=excluded.updated_at, last_seen_at=excluded.last_seen_at
            """,
            (lock_id, json.dumps([args.claimed_label], sort_keys=True), ts, ts, ts),
        )
    print(
        json.dumps(
            {
                "ok": True,
                "claimed": True,
                "issue": {"number": issue_number, "external_id": row["external_id"], "title": row["title"]},
                "added_label": args.claimed_label,
                "removed_ready_label": bool(args.remove_ready_label),
                "lock": lock_id,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def append_label_json(labels_json: str | None, label: str) -> str:
    labels = json.loads(labels_json or "[]")
    if label not in labels:
        labels.append(label)
    return json.dumps(sorted(labels), sort_keys=True)


def fetch_check_runs(owner: str, repo: str, sha: str, token: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"per_page": "100"})
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}/check-runs?{query}"
    data, _ = github_api_get(url, token)
    return data.get("check_runs", [])


def latest_named_check(check_runs: list[dict[str, Any]], name: str, app_slug: str | None = None) -> dict[str, Any] | None:
    matches = [check for check in check_runs if check.get("name") == name]
    if app_slug:
        matches = [check for check in matches if ((check.get("app") or {}).get("slug") == app_slug)]
    if not matches:
        return None
    return sorted(matches, key=lambda c: c.get("started_at") or c.get("created_at") or "", reverse=True)[0]


def add_issue_label(owner: str, repo: str, issue_number: int, label: str, token: str) -> None:
    labels_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/labels"
    github_api_post(labels_url, token, {"labels": [label]})


def remove_issue_label(owner: str, repo: str, issue_number: int, label: str, token: str) -> None:
    encoded = urllib.parse.quote(label, safe="")
    github_request("DELETE", f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/labels/{encoded}", token)


def create_approval_request_outbox(
    conn: sqlite3.Connection,
    *,
    pr_number: int,
    title: str,
    url: str,
    reason: str,
    risk_summary: str,
) -> tuple[str, bool]:
    ts = now_iso()
    external_id = f"approval-pr-{pr_number}"
    payload = {
        "type": "approval_request",
        "pr": pr_number,
        "title": title,
        "reason": reason,
        "risk_summary": risk_summary,
        "url": url,
        "allowed_replies": ["approve", "reject"],
    }
    message = (
        f"Approval required for PR #{pr_number}: {title}\n"
        f"Reason: {reason}\n"
        f"Risk: {risk_summary}\n"
        f"URL: {url}\n"
        "Reply approve or reject."
    )
    existing = conn.execute("SELECT state FROM outbox WHERE external_id=?", (external_id,)).fetchone()
    if existing:
        return external_id, False
    conn.execute(
        """
        INSERT INTO outbox(external_id, state, labels, channel, message, payload_json, created_at, updated_at, last_seen_at, retry_count)
        VALUES (?, 'pending', ?, 'whatsapp', ?, ?, ?, ?, ?, 0)
        """,
        (external_id, json.dumps(["approval_request"], sort_keys=True), message, json.dumps(payload, sort_keys=True), ts, ts, ts),
    )
    return external_id, True


def record_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    entity_type: str,
    entity_external_id: str | None,
    state: str,
    payload: dict[str, Any],
) -> str:
    ts = now_iso()
    external_id = f"{event_type}-{entity_type}-{entity_external_id or 'none'}-{ts}"
    conn.execute(
        """
        INSERT INTO events(external_id, entity_type, entity_external_id, event_type, state, payload_json, created_at, updated_at, last_seen_at, retry_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (external_id, entity_type, entity_external_id, event_type, state, json.dumps(payload, sort_keys=True), ts, ts, ts),
    )
    return external_id


def is_auto_merge_candidate(labels: list[str], review_check: dict[str, Any] | None, branch: str = "") -> tuple[bool, str]:
    if not branch.startswith("agent/issue-"):
        return False, "untrusted_branch"
    if "agent:pr-opened" not in labels:
        return False, "missing_agent_pr_opened"
    if "agent:needs-fix" in labels or "review-failed" in labels:
        return False, "needs_fix"
    if "agent:blocked" in labels:
        return False, "blocked"
    if not review_check:
        return False, "missing_review_check"
    if review_check.get("status") != "completed" or review_check.get("conclusion") != "success":
        return False, "review_not_successful"
    return True, "ok"


def create_blocked_outbox(
    conn: sqlite3.Connection,
    *,
    pr_number: int,
    title: str,
    url: str,
    reason: str,
    retry_count: int,
) -> tuple[str, bool]:
    ts = now_iso()
    external_id = f"blocked-pr-{pr_number}"
    payload = {
        "type": "blocked_pr",
        "pr": pr_number,
        "title": title,
        "reason": reason,
        "retry_count": retry_count,
        "url": url,
    }
    message = (
        f"PR #{pr_number} is blocked: {title}\n"
        f"Reason: {reason}\n"
        f"Retry count: {retry_count}\n"
        f"URL: {url}"
    )
    existing = conn.execute("SELECT state FROM outbox WHERE external_id=?", (external_id,)).fetchone()
    if existing:
        return external_id, False
    conn.execute(
        """
        INSERT INTO outbox(external_id, state, labels, channel, message, payload_json, created_at, updated_at, last_seen_at, retry_count)
        VALUES (?, 'pending', ?, 'whatsapp', ?, ?, ?, ?, ?, 0)
        """,
        (external_id, json.dumps(["blocked", "review_failure"], sort_keys=True), message, json.dumps(payload, sort_keys=True), ts, ts, ts),
    )
    return external_id, True


def cmd_enable_auto_merge(args: argparse.Namespace) -> int:
    init_db(args.db)
    token = mint_github_token(args.token_cmd)
    mutation = """
    mutation EnableAutoMerge($pullRequestId: ID!) {
      enablePullRequestAutoMerge(input: {pullRequestId: $pullRequestId, mergeMethod: SQUASH}) {
        pullRequest { number autoMergeRequest { enabledAt mergeMethod } }
      }
    }
    """
    results: list[dict[str, Any]] = []
    with connect(args.db) as conn:
        rows = conn.execute(
            """
            SELECT external_id, number, state, labels, branch, payload_json
            FROM pull_requests
            WHERE state='open'
            ORDER BY number ASC
            """
        ).fetchall()
        for row in rows:
            pr_number = int(row["number"])
            labels = fetch_issue_labels(args.owner, args.repo, pr_number, token)
            if "human:rejected" in labels:
                payload = {"pr": pr_number, "labels": labels, "reason": "human_rejected"}
                event_id = record_event(
                    conn,
                    event_type="auto_merge_skipped",
                    entity_type="pull_request",
                    entity_external_id=row["external_id"],
                    state="skipped",
                    payload=payload,
                )
                results.append({"pr": pr_number, "enabled": False, "skipped": True, "reason": "human_rejected", "event": event_id})
                continue
            if "needs:human-approval" in labels and "human:approved" not in labels:
                pr_payload = json.loads(row["payload_json"] or "{}")
                outbox_id, created = create_approval_request_outbox(
                    conn,
                    pr_number=pr_number,
                    title=pr_payload.get("title") or f"PR #{pr_number}",
                    url=pr_payload.get("html_url") or f"https://github.com/{args.owner}/{args.repo}/pull/{pr_number}",
                    reason="PR is labeled needs:human-approval",
                    risk_summary="Manual approval gate is active; auto-merge is paused until approve/reject.",
                )
                payload = {"pr": pr_number, "labels": labels, "reason": "needs_human_approval", "outbox_id": outbox_id, "outbox_created": created}
                event_id = record_event(
                    conn,
                    event_type="approval_request_queued" if created else "approval_request_existing",
                    entity_type="pull_request",
                    entity_external_id=row["external_id"],
                    state="pending",
                    payload=payload,
                )
                results.append({"pr": pr_number, "enabled": False, "skipped": True, "reason": "needs_human_approval", "outbox_id": outbox_id, "outbox_created": created, "event": event_id})
                continue
            current_pr = fetch_pr(args.owner, args.repo, pr_number, token)
            pr_payload = current_pr
            head_sha = ((current_pr.get("head") or {}).get("sha") or "")
            review_check = latest_named_check(fetch_check_runs(args.owner, args.repo, head_sha, token), args.review_check_name, args.review_app_slug) if head_sha else None
            branch = ((current_pr.get("head") or {}).get("ref")) or str(row["branch"] or "")
            if not is_trusted_agent_pr(current_pr):
                payload = {"pr": pr_number, "reason": "untrusted_pr", "branch": branch, "head_sha": head_sha}
                event_id = record_event(
                    conn,
                    event_type="auto_merge_skipped",
                    entity_type="pull_request",
                    entity_external_id=row["external_id"],
                    state="skipped",
                    payload=payload,
                )
                results.append({"pr": pr_number, "enabled": False, "skipped": True, "reason": "untrusted_pr", "event": event_id})
                continue
            if (review_check or {}).get("status") == "completed" and (review_check or {}).get("conclusion") == "success" and "agent:needs-fix" in labels:
                try:
                    remove_issue_label(args.owner, args.repo, pr_number, "agent:needs-fix", token)
                except urllib.error.HTTPError as exc:
                    if exc.code not in {403, 404}:
                        raise
                labels = [label for label in labels if label not in {"agent:needs-fix", "review-failed"}]
            conn.execute(
                "UPDATE pull_requests SET branch=?, labels=?, payload_json=?, updated_at=?, last_seen_at=? WHERE external_id=?",
                (branch, json.dumps(labels, sort_keys=True), json.dumps(current_pr, sort_keys=True), now_iso(), now_iso(), row["external_id"]),
            )
            candidate, reason = is_auto_merge_candidate(labels, review_check, branch)
            if not candidate:
                payload = {"pr": pr_number, "labels": labels, "reason": reason, "review_check": review_check}
                event_id = record_event(
                    conn,
                    event_type="auto_merge_skipped",
                    entity_type="pull_request",
                    entity_external_id=row["external_id"],
                    state="skipped",
                    payload=payload,
                )
                results.append({"pr": pr_number, "enabled": False, "skipped": True, "reason": reason, "event": event_id})
                continue
            node_id = pr_payload.get("node_id")
            if not node_id:
                payload = {"pr": pr_number, "reason": "missing_node_id"}
                event_id = record_event(
                    conn,
                    event_type="auto_merge_failed",
                    entity_type="pull_request",
                    entity_external_id=row["external_id"],
                    state="failed",
                    payload=payload,
                )
                results.append({"pr": pr_number, "enabled": False, "error": "missing_node_id", "event": event_id})
                continue
            try:
                data = github_graphql(token, mutation, {"pullRequestId": node_id})
                payload = {"pr": pr_number, "result": data}
                event_id = record_event(
                    conn,
                    event_type="auto_merge_enabled",
                    entity_type="pull_request",
                    entity_external_id=row["external_id"],
                    state="succeeded",
                    payload=payload,
                )
                results.append({"pr": pr_number, "enabled": True, "event": event_id})
            except Exception as exc:  # GitHub can reject when already mergeable/clean, checks are missing, or permissions are insufficient.
                error = str(exc)
                if "Pull request is in clean status" in error:
                    merge_data = merge_pull_request(args.owner, args.repo, pr_number, token, head_sha)
                    branch_deleted = delete_branch_ref(args.owner, args.repo, branch, token)
                    payload = {"pr": pr_number, "reason": "clean_status_direct_merge", "merge": merge_data, "branch": branch, "branch_deleted": branch_deleted}
                    event_id = record_event(
                        conn,
                        event_type="auto_merge_direct_merged",
                        entity_type="pull_request",
                        entity_external_id=row["external_id"],
                        state="succeeded",
                        payload=payload,
                    )
                    results.append({"pr": pr_number, "enabled": False, "merged": True, "reason": "clean_status_direct_merge", "branch_deleted": branch_deleted, "event": event_id})
                    continue
                payload = {"pr": pr_number, "error": error, "node_id": node_id}
                event_id = record_event(
                    conn,
                    event_type="auto_merge_failed",
                    entity_type="pull_request",
                    entity_external_id=row["external_id"],
                    state="failed",
                    payload=payload,
                )
                results.append({"pr": pr_number, "enabled": False, "error": error, "event": event_id})
    print(json.dumps({"ok": True, "command": "enable-auto-merge", "results": results}, indent=2, sort_keys=True))
    return 0


def cmd_route_review_failures(args: argparse.Namespace) -> int:
    init_db(args.db)
    token = mint_github_token(args.token_cmd)
    results: list[dict[str, Any]] = []
    with connect(args.db) as conn:
        rows = conn.execute(
            """
            SELECT external_id, number, issue_external_id, branch, state, labels, payload_json, retry_count
            FROM pull_requests
            WHERE state='open'
            ORDER BY number ASC
            """
        ).fetchall()
        for row in rows:
            pr_number = int(row["number"])
            pr_payload = json.loads(row["payload_json"] or "{}")
            sha = ((pr_payload.get("head") or {}).get("sha")) or ""
            if not sha:
                event_id = record_event(
                    conn,
                    event_type="review_failure_route_failed",
                    entity_type="pull_request",
                    entity_external_id=row["external_id"],
                    state="failed",
                    payload={"pr": pr_number, "reason": "missing_head_sha"},
                )
                results.append({"pr": pr_number, "routed": False, "reason": "missing_head_sha", "event": event_id})
                continue
            check = latest_named_check(fetch_check_runs(args.owner, args.repo, sha, token), args.review_check_name, args.review_app_slug)
            conclusion = (check or {}).get("conclusion")
            status = (check or {}).get("status")
            if conclusion not in {"failure", "timed_out", "cancelled", "action_required"}:
                results.append(
                    {
                        "pr": pr_number,
                        "routed": False,
                        "reason": "no_failed_review_check",
                        "check": {"name": args.review_check_name, "status": status, "conclusion": conclusion},
                    }
                )
                continue
            live_labels = fetch_issue_labels(args.owner, args.repo, pr_number, token)
            stored_labels = json.loads(row["labels"] or "[]")
            labels = sorted(set(live_labels) | set(stored_labels))
            branch = ((pr_payload.get("head") or {}).get("ref")) or str(row["branch"] or "")
            previous_success = conn.execute(
                """
                SELECT id FROM events
                WHERE entity_external_id=? AND event_type='review_failure_routed' AND state='succeeded' AND payload_json LIKE ?
                LIMIT 1
                """,
                (row["external_id"], f'%"head_sha": "{sha}"%'),
            ).fetchone()
            if previous_success:
                results.append({"pr": pr_number, "routed": False, "reason": "already_routed_failed_review", "check": check})
                continue
            if not branch.startswith("agent/issue-") or "agent:pr-opened" not in labels:
                event_id = record_event(
                    conn,
                    event_type="review_failure_route_skipped",
                    entity_type="pull_request",
                    entity_external_id=row["external_id"],
                    state="skipped",
                    payload={"pr": pr_number, "reason": "untrusted_pr", "branch": branch, "labels": labels},
                )
                results.append({"pr": pr_number, "routed": False, "reason": "untrusted_pr", "event": event_id})
                continue
            current_retry = int(row["retry_count"] or 0) + 1
            if current_retry > args.max_review_fix_retries:
                pr_payload = json.loads(row["payload_json"] or "{}")
                try:
                    add_issue_label(args.owner, args.repo, pr_number, "agent:blocked", token)
                    add_issue_label(args.owner, args.repo, pr_number, "needs:human-approval", token)
                    github_label_updated = True
                except urllib.error.HTTPError as exc:
                    if exc.code not in {403, 404}:
                        raise
                    github_label_updated = False
                outbox_id, outbox_created = create_blocked_outbox(
                    conn,
                    pr_number=pr_number,
                    title=pr_payload.get("title") or f"PR #{pr_number}",
                    url=pr_payload.get("html_url") or f"https://github.com/{args.owner}/{args.repo}/pull/{pr_number}",
                    reason=f"Review failed more than {args.max_review_fix_retries} retry attempts",
                    retry_count=current_retry,
                )
                labels = append_label_json(append_label_json(row["labels"], "agent:blocked"), "needs:human-approval")
                event_id = record_event(
                    conn,
                    event_type="review_failure_retry_limit",
                    entity_type="pull_request",
                    entity_external_id=row["external_id"],
                    state="blocked",
                    payload={"pr": pr_number, "retry_count": current_retry, "max_retries": args.max_review_fix_retries, "outbox_id": outbox_id, "outbox_created": outbox_created, "github_label_updated": github_label_updated},
                )
                conn.execute(
                    "UPDATE pull_requests SET retry_count=?, labels=?, updated_at=?, last_seen_at=? WHERE external_id=?",
                    (current_retry, labels, now_iso(), now_iso(), row["external_id"]),
                )
                results.append({"pr": pr_number, "routed": False, "reason": "retry_limit", "event": event_id, "outbox_id": outbox_id, "outbox_created": outbox_created, "github_label_updated": github_label_updated})
                continue
            try:
                add_issue_label(args.owner, args.repo, pr_number, "agent:needs-fix", token)
                github_label_updated = True
            except urllib.error.HTTPError as exc:
                if exc.code not in {403, 404}:
                    raise
                github_label_updated = False
            ts = now_iso()
            labels = append_label_json(append_label_json(row["labels"], "agent:needs-fix"), "review-failed")
            conn.execute(
                "UPDATE pull_requests SET retry_count=?, labels=?, updated_at=?, last_seen_at=? WHERE external_id=?",
                (current_retry, labels, ts, ts, row["external_id"]),
            )
            attempt_external_id = f"pr-{pr_number}-review-fix-attempt-{ts}"
            conn.execute(
                """
                INSERT INTO attempts(
                  external_id, entity_type, entity_external_id, state, labels,
                  created_at, updated_at, last_seen_at, retry_count, started_at
                ) VALUES (?, 'pull_request', ?, 'started', ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_external_id,
                    row["external_id"],
                    json.dumps(["coding-stub", "review-fix"], sort_keys=True),
                    ts,
                    ts,
                    ts,
                    current_retry,
                    ts,
                ),
            )
            issue_row = None
            if row["issue_external_id"]:
                issue_row = conn.execute("SELECT number FROM issues WHERE external_id=?", (row["issue_external_id"],)).fetchone()
            if not issue_row:
                event_id = record_event(
                    conn,
                    event_type="review_failure_route_failed",
                    entity_type="pull_request",
                    entity_external_id=row["external_id"],
                    state="failed",
                    payload={"pr": pr_number, "reason": "missing_linked_issue"},
                )
                results.append({"pr": pr_number, "routed": False, "reason": "missing_linked_issue", "event": event_id})
                continue
            issue_number = int(issue_row["number"])
            cmd = [
                args.coding_agent_cmd,
                "run",
                "--issue",
                str(issue_number),
                "--fix-pr",
                str(pr_number),
            ]
            try:
                proc = subprocess.run(cmd, text=True, capture_output=True, timeout=args.timeout_seconds)
                returncode = proc.returncode
                stdout = proc.stdout
                stderr = proc.stderr
            except subprocess.TimeoutExpired as exc:
                returncode = 124
                stdout = exc.stdout or ""
                stderr = (exc.stderr or "") + "\nCommand timed out"
            finished = now_iso()
            state = "succeeded" if returncode == 0 else "failed"
            result = {"returncode": returncode, "stdout": redact_text(stdout), "stderr": redact_text(stderr), "command": cmd, "check": check}
            conn.execute(
                """
                UPDATE attempts
                SET state=?, updated_at=?, last_seen_at=?, finished_at=?, result_json=?
                WHERE external_id=?
                """,
                (state, finished, finished, finished, json.dumps(result, sort_keys=True), attempt_external_id),
            )
            event_id = record_event(
                conn,
                event_type="review_failure_routed",
                entity_type="pull_request",
                entity_external_id=row["external_id"],
                state=state,
                payload={
                    "pr": pr_number,
                    "issue": issue_number,
                    "head_sha": sha,
                    "check": check,
                    "attempt": attempt_external_id,
                    "github_label_updated": github_label_updated,
                    "retry_count": current_retry,
                },
            )
            results.append(
                {
                    "pr": pr_number,
                    "routed": returncode == 0,
                    "attempt": attempt_external_id,
                    "event": event_id,
                    "retry_count": current_retry,
                    "github_label_updated": github_label_updated,
                    "state": state,
                }
            )
    print(json.dumps({"ok": True, "command": "route-review-failures", "results": results}, indent=2, sort_keys=True))
    return 0


def cmd_dispatch_coding_stub(args: argparse.Namespace) -> int:
    init_db(args.db)
    with connect(args.db) as conn:
        row = conn.execute(
            """
            SELECT external_id, number, title, retry_count
            FROM issues
            WHERE state='open' AND labels LIKE ?
            ORDER BY number ASC
            LIMIT 1
            """,
            (f'%"{args.claimed_label}"%',),
        ).fetchone()
        if not row:
            print(json.dumps({"ok": True, "dispatched": False, "reason": "no_claimed_issue"}, indent=2, sort_keys=True))
            return 0
        ts = now_iso()
        attempt_external_id = f"issue-{row['number']}-coding-attempt-{ts}"
        conn.execute(
            """
            INSERT INTO attempts(
              external_id, entity_type, entity_external_id, state, labels,
              created_at, updated_at, last_seen_at, retry_count, started_at
            ) VALUES (?, 'issue', ?, 'started', ?, ?, ?, ?, 0, ?)
            """,
            (
                attempt_external_id,
                row["external_id"],
                json.dumps(["coding-stub"], sort_keys=True),
                ts,
                ts,
                ts,
                ts,
            ),
        )
    cmd = [
        args.coding_stub_cmd,
        "--issue-number",
        str(row["number"]),
        "--issue-external-id",
        str(row["external_id"]),
        "--title",
        row["title"],
    ]
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=args.timeout_seconds)
        returncode = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + "\nCommand timed out"
    finished = now_iso()
    state = "succeeded" if returncode == 0 else "failed"
    result = {
        "returncode": returncode,
        "stdout": redact_text(stdout),
        "stderr": redact_text(stderr),
        "command": cmd,
    }
    with connect(args.db) as conn:
        conn.execute(
            """
            UPDATE attempts
            SET state=?, updated_at=?, last_seen_at=?, finished_at=?, result_json=?
            WHERE external_id=?
            """,
            (state, finished, finished, finished, json.dumps(result, sort_keys=True), attempt_external_id),
        )
    print(
        json.dumps(
            {
                "ok": returncode == 0,
                "dispatched": True,
                "attempt": attempt_external_id,
                "state": state,
                "issue": {"number": row["number"], "external_id": row["external_id"], "title": row["title"]},
                "stdout": redact_text(stdout),
                "stderr": redact_text(stderr),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if returncode == 0 else returncode


def cmd_finalize_merged(args: argparse.Namespace) -> int:
    init_db(args.db)
    token = mint_github_token(args.token_cmd)
    finalized: list[dict[str, Any]] = []
    with connect(args.db) as conn:
        rows = conn.execute("SELECT external_id, number, issue_external_id, state FROM pull_requests WHERE state != 'merged' ORDER BY number ASC").fetchall()
        for row in rows:
            pr_number = int(row["number"])
            pr, _ = github_api_get(f"https://api.github.com/repos/{args.owner}/{args.repo}/pulls/{pr_number}", token)
            if not pr.get("merged_at"):
                continue
            ts = now_iso()
            conn.execute(
                "UPDATE pull_requests SET state='merged', payload_json=?, updated_at=?, last_seen_at=? WHERE external_id=?",
                (json.dumps(pr, sort_keys=True), ts, ts, row["external_id"]),
            )
            issue_external_id = row["issue_external_id"]
            issue_number = None
            if issue_external_id:
                issue_row = conn.execute("SELECT number FROM issues WHERE external_id=?", (issue_external_id,)).fetchone()
                if issue_row:
                    issue_number = int(issue_row["number"])
                    github_api_post(
                        f"https://api.github.com/repos/{args.owner}/{args.repo}/issues/{issue_number}/comments",
                        token,
                        {"body": f"/agent-completed via merged PR #{pr_number}"},
                    )
                    github_request(
                        "PATCH",
                        f"https://api.github.com/repos/{args.owner}/{args.repo}/issues/{issue_number}",
                        token,
                        {"state": "closed", "state_reason": "completed"},
                    )
                    refreshed, _ = github_api_get(f"https://api.github.com/repos/{args.owner}/{args.repo}/issues/{issue_number}", token)
                    upsert_issue(conn, refreshed)
            record_event(
                conn,
                event_type="pr_finalized",
                entity_type="pull_request",
                entity_external_id=row["external_id"],
                state="succeeded",
                payload={"pr": pr_number, "issue": issue_number, "merged_at": pr.get("merged_at")},
            )
            finalized.append({"pr": pr_number, "issue": issue_number, "merged_at": pr.get("merged_at")})
    print(json.dumps({"ok": True, "command": "finalize-merged", "finalized": finalized}, indent=2, sort_keys=True))
    return 0


def cmd_outbox_next(args: argparse.Namespace) -> int:
    init_db(args.db)
    with connect(args.db) as conn:
        row = conn.execute(
            "SELECT * FROM outbox WHERE state='pending' ORDER BY created_at, id LIMIT 1"
        ).fetchone()
    if not row:
        print(json.dumps({"type": "none"}, indent=2, sort_keys=True))
        return 0
    payload = json.loads(row["payload_json"] or "{}")
    message_type = payload.get("type") or "message"
    result: dict[str, Any] = {
        "type": message_type,
        "id": row["external_id"],
        "body": row["message"],
    }
    if row["channel"]:
        result["channel"] = row["channel"]
    for key in ["pr", "issue", "title", "decision", "url", "labels"]:
        if key in payload:
            result[key] = payload[key]
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_inbox_ack(args: argparse.Namespace) -> int:
    init_db(args.db)
    token = mint_github_token(args.token_cmd)
    label = "human:approved" if args.decision == "approve" else "human:rejected"
    comment = "/human-approved" if args.decision == "approve" else "/human-rejected"
    ts = now_iso()
    with connect(args.db) as conn:
        outbox = conn.execute("SELECT * FROM outbox WHERE external_id=?", (args.outbox_id,)).fetchone()
        if not outbox:
            print(json.dumps({"ok": False, "reason": "outbox_not_found", "outbox_id": args.outbox_id}, indent=2, sort_keys=True))
            return 1
        if outbox["state"] != "pending":
            print(json.dumps({"ok": False, "reason": "outbox_not_pending", "outbox_id": args.outbox_id}, indent=2, sort_keys=True))
            return 1
        payload = json.loads(outbox["payload_json"] or "{}")
        if payload.get("type") != "approval_request" or args.decision not in payload.get("allowed_replies", []):
            print(json.dumps({"ok": False, "reason": "not_an_approval_request", "outbox_id": args.outbox_id}, indent=2, sort_keys=True))
            return 1
        target_number = payload.get("pr") or payload.get("issue")
        if not target_number:
            print(json.dumps({"ok": False, "reason": "missing_pr_or_issue", "outbox_id": args.outbox_id}, indent=2, sort_keys=True))
            return 1
        target_number = int(target_number)
        labels_url = f"https://api.github.com/repos/{args.owner}/{args.repo}/issues/{target_number}/labels"
        comments_url = f"https://api.github.com/repos/{args.owner}/{args.repo}/issues/{target_number}/comments"
        github_api_post(labels_url, token, {"labels": [label]})
        github_api_post(comments_url, token, {"body": comment})
        conn.execute(
            "UPDATE outbox SET state='acknowledged', updated_at=?, last_seen_at=? WHERE external_id=?",
            (ts, ts, args.outbox_id),
        )
        inbox_external_id = f"ack-{args.outbox_id}-{ts}"
        inbox_payload = {
            "outbox_id": args.outbox_id,
            "decision": args.decision,
            "label": label,
            "comment": comment,
            "target_number": target_number,
            "target_type": "pr" if "pr" in payload else "issue",
        }
        conn.execute(
            """
            INSERT INTO inbox(external_id, state, labels, source, message, payload_json, created_at, updated_at, last_seen_at, retry_count, acknowledged_at)
            VALUES (?, 'acknowledged', ?, 'openclaw', ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                inbox_external_id,
                json.dumps([label], sort_keys=True),
                args.decision,
                json.dumps(inbox_payload, sort_keys=True),
                ts,
                ts,
                ts,
                ts,
            ),
        )
    print(
        json.dumps(
            {
                "ok": True,
                "outbox_id": args.outbox_id,
                "decision": args.decision,
                "target_number": target_number,
                "label": label,
                "comment": comment,
                "inbox_id": inbox_external_id,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_db_init(args: argparse.Namespace) -> int:
    init_db(args.db)
    print(json.dumps({"ok": True, "db_path": str(args.db)}, sort_keys=True))
    return 0


def cmd_db_backup(args: argparse.Namespace) -> int:
    init_db(args.db)
    args.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = args.backup_dir / f"orchestrator-{stamp}.db"
    with sqlite3.connect(args.db) as src, sqlite3.connect(dest) as dst:
        src.backup(dst)
    dest.chmod(0o600)
    print(json.dumps({"ok": True, "source": str(args.db), "backup": str(dest)}, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="trading-orchestrator")
    p.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    p.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    p.add_argument("--owner", default=DEFAULT_GITHUB_OWNER)
    p.add_argument("--repo", default=DEFAULT_GITHUB_REPO)
    p.add_argument("--ready-label", default=DEFAULT_READY_LABEL)
    p.add_argument("--claimed-label", default=DEFAULT_CLAIMED_LABEL)
    p.add_argument("--token-cmd", default=DEFAULT_TOKEN_CMD)
    p.add_argument("--coding-stub-cmd", default=DEFAULT_CODING_STUB_CMD)
    p.add_argument("--coding-agent-cmd", default=DEFAULT_CODING_AGENT_CMD)
    sub = p.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status")
    status.set_defaults(func=cmd_status)

    scan = sub.add_parser("scan")
    scan.set_defaults(func=cmd_scan)

    scan_prs = sub.add_parser("scan-prs")
    scan_prs.set_defaults(func=cmd_scan_prs)

    claim = sub.add_parser("claim")
    claim.add_argument("--max-claimed", type=int, default=2)
    claim.add_argument("--keep-ready-label", dest="remove_ready_label", action="store_false", default=True)
    claim.set_defaults(func=cmd_claim)

    auto_merge = sub.add_parser("enable-auto-merge")
    auto_merge.add_argument("--review-check-name", default=DEFAULT_REVIEW_CHECK_NAME)
    auto_merge.add_argument("--review-app-slug", default=DEFAULT_REVIEW_APP_SLUG)
    auto_merge.set_defaults(func=cmd_enable_auto_merge)

    route_review = sub.add_parser("route-review-failures")
    route_review.add_argument("--review-check-name", default=DEFAULT_REVIEW_CHECK_NAME)
    route_review.add_argument("--review-app-slug", default=DEFAULT_REVIEW_APP_SLUG)
    route_review.add_argument("--max-review-fix-retries", type=int, default=DEFAULT_MAX_REVIEW_FIX_RETRIES)
    route_review.add_argument("--timeout-seconds", type=int, default=60)
    route_review.set_defaults(func=cmd_route_review_failures)

    finalize = sub.add_parser("finalize-merged")
    finalize.set_defaults(func=cmd_finalize_merged)

    dispatch = sub.add_parser("dispatch")
    dispatch_sub = dispatch.add_subparsers(dest="dispatch_command", required=True)
    dispatch_coding_stub = dispatch_sub.add_parser("coding-stub")
    dispatch_coding_stub.add_argument("--timeout-seconds", type=int, default=60)
    dispatch_coding_stub.set_defaults(func=cmd_dispatch_coding_stub)

    outbox = sub.add_parser("outbox")
    outbox_sub = outbox.add_subparsers(dest="outbox_command", required=True)
    outbox_next = outbox_sub.add_parser("next")
    outbox_next.set_defaults(func=cmd_outbox_next)

    inbox = sub.add_parser("inbox")
    inbox_sub = inbox.add_subparsers(dest="inbox_command", required=True)
    inbox_ack = inbox_sub.add_parser("ack")
    inbox_ack.add_argument("--outbox-id", required=True)
    inbox_ack.add_argument("--decision", required=True, choices=["approve", "reject"])
    inbox_ack.set_defaults(func=cmd_inbox_ack)

    db = sub.add_parser("db")
    db_sub = db.add_subparsers(dest="db_command", required=True)
    db_init = db_sub.add_parser("init")
    db_init.set_defaults(func=cmd_db_init)
    db_backup = db_sub.add_parser("backup")
    db_backup.set_defaults(func=cmd_db_backup)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
