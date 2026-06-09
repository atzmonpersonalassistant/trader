#!/usr/bin/env python3
"""
GitHub App Manifest flow helper for MVP-0 trading agents.

Usage:
  python3 agent-platform/tools/github_app_manifest_flow.py serve

Then open:
  http://127.0.0.1:8787/

For each app:
  1. Click the app link.
  2. GitHub opens the prefilled App Manifest creation page.
  3. Approve/create/install the app in GitHub UI.
  4. GitHub redirects back to this helper with a code.
  5. The helper converts the code into app metadata + private key.

Private keys are saved outside git:
  ~/.trading-agents/github-apps/<role>.private-key.pem

Metadata is saved outside git:
  ~/.trading-agents/github-apps/<role>.app.json
"""

from __future__ import annotations

import argparse
import html
import json
import os
import stat
import sys
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8787
BASE_URL = f"http://{HOST}:{PORT}"
GITHUB_NEW_APP_URL = "https://github.com/settings/apps/new"
OUT_DIR = Path.home() / ".trading-agents" / "github-apps"

REPO_URL = "https://github.com/atzmonpersonalassistant/trader"

APPS = {
    "orchestrator": {
        "name": "trading-orchestrator-agent",
        "description": "MVP-0 orchestrator: polling, labels, comments, state, and auto-merge enablement. No code writes.",
        "permissions": {
            "issues": "write",
            "pull_requests": "read",
            "checks": "read",
            "actions": "read",
            "contents": "read",
        },
    },
    "coding": {
        "name": "trading-coding-agent",
        "description": "MVP-0 coding agent: reads issues, creates branches, pushes changes, opens PRs, and fixes review failures.",
        "permissions": {
            "contents": "write",
            "issues": "write",
            "pull_requests": "write",
            "checks": "read",
            "actions": "read",
        },
    },
    "review": {
        "name": "trading-review-agent",
        "description": "MVP-0 review agent: reads PR diffs and publishes the required Review Agent check/review.",
        "permissions": {
            "contents": "read",
            "pull_requests": "write",
            "checks": "write",
            "issues": "read",
            "actions": "read",
        },
    },
    "validator": {
        "name": "trading-validator-agent",
        "description": "Placeholder for MVP-1+ quant validator. Not required by MVP-0 branch protection.",
        "permissions": {
            "contents": "read",
            "pull_requests": "write",
            "checks": "write",
            "issues": "write",
            "actions": "read",
        },
    },
}


def manifest_for(role: str) -> dict:
    spec = APPS[role]
    return {
        "name": spec["name"],
        "url": REPO_URL,
        "description": spec["description"],
        "redirect_url": f"{BASE_URL}/callback?role={urllib.parse.quote(role)}",
        "callback_urls": [f"{BASE_URL}/callback?role={urllib.parse.quote(role)}"],
        "public": False,
        "default_permissions": spec["permissions"],
        "default_events": [],
    }


def convert_manifest_code(role: str, code: str) -> dict:
    url = f"https://api.github.com/app-manifests/{urllib.parse.quote(code)}/conversions"
    req = urllib.request.Request(
        url,
        method="POST",
        headers={"Accept": "application/vnd.github+json"},
        data=b"{}",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pem = data.get("pem")
    if pem:
        pem_path = OUT_DIR / f"{role}.private-key.pem"
        pem_path.write_text(pem)
        os.chmod(pem_path, stat.S_IRUSR | stat.S_IWUSR)

    redacted = dict(data)
    if "pem" in redacted:
        redacted["pem"] = f"<saved to {OUT_DIR / (role + '.private-key.pem')}>"

    meta_path = OUT_DIR / f"{role}.app.json"
    meta_path.write_text(json.dumps(redacted, indent=2, sort_keys=True) + "\n")
    os.chmod(meta_path, stat.S_IRUSR | stat.S_IWUSR)
    return redacted


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def send_html(self, body: str, status: int = 200):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            links = "".join(
                f"<li><a href='/manifest/{html.escape(role)}'>{html.escape(spec['name'])}</a> — {html.escape(role)}</li>"
                for role, spec in APPS.items()
            )
            self.send_html(f"""
            <html><body>
            <h1>MVP-0 GitHub App Manifest Flow</h1>
            <p>Create the apps one by one. GitHub will ask you to approve/install each app.</p>
            <ul>{links}</ul>
            <p>Private keys/metadata are saved outside git under <code>{html.escape(str(OUT_DIR))}</code>.</p>
            </body></html>
            """)
            return

        if path.startswith("/manifest/"):
            role = path.split("/", 2)[2]
            if role not in APPS:
                self.send_html("Unknown role", 404)
                return
            manifest = json.dumps(manifest_for(role), separators=(",", ":"))
            pretty = json.dumps(manifest_for(role), indent=2)
            self.send_html(f"""
            <html><body onload="document.forms[0].submit()">
            <h1>Creating {html.escape(APPS[role]['name'])}</h1>
            <p>If you are not redirected automatically, click Submit.</p>
            <form action="{GITHUB_NEW_APP_URL}" method="post">
              <input type="hidden" name="manifest" value="{html.escape(manifest, quote=True)}" />
              <button type="submit">Submit manifest to GitHub</button>
            </form>
            <h2>Manifest preview</h2>
            <pre>{html.escape(pretty)}</pre>
            </body></html>
            """)
            return

        if path == "/callback":
            role = (qs.get("role") or [""])[0]
            code = (qs.get("code") or [""])[0]
            if role not in APPS:
                self.send_html("Missing/unknown role in callback", 400)
                return
            if not code:
                self.send_html("Missing code in callback", 400)
                return
            try:
                data = convert_manifest_code(role, code)
            except Exception as e:
                self.send_html(f"<h1>Conversion failed</h1><pre>{html.escape(repr(e))}</pre>", 500)
                return
            self.send_html(f"""
            <html><body>
            <h1>Created {html.escape(APPS[role]['name'])}</h1>
            <p>Saved metadata and private key under <code>{html.escape(str(OUT_DIR))}</code>.</p>
            <p>Now install the app on <code>atzmonpersonalassistant/trader</code> if GitHub did not already prompt installation.</p>
            <h2>Metadata</h2>
            <pre>{html.escape(json.dumps(data, indent=2, sort_keys=True))}</pre>
            <p><a href='/'>Back to app list</a></p>
            </body></html>
            """)
            return

        self.send_html("Not found", 404)


def serve():
    print(f"Serving GitHub App manifest flow at {BASE_URL}/")
    print(f"Output directory: {OUT_DIR}")
    HTTPServer((HOST, PORT), Handler).serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["serve", "manifest"])
    parser.add_argument("role", nargs="?", choices=sorted(APPS))
    args = parser.parse_args()

    if args.command == "serve":
        serve()
    elif args.command == "manifest":
        if not args.role:
            parser.error("manifest requires role")
        print(json.dumps(manifest_for(args.role), indent=2))


if __name__ == "__main__":
    main()
