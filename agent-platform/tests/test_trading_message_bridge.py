import importlib.machinery
import importlib.util
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "agent-platform" / "scripts" / "trading-message-bridge"
loader = importlib.machinery.SourceFileLoader("trading_message_bridge", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
bridge = importlib.util.module_from_spec(spec)
loader.exec_module(bridge)


class _Handler(BaseHTTPRequestHandler):
    response = {"ok": True, "last_row": 3, "messages": []}
    requests = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        request_body = self.rfile.read(length).decode("utf-8") if length else ""
        self.__class__.requests.append({"path": self.path, "body": request_body, "headers": dict(self.headers)})
        body = json.dumps(self.__class__.response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        return


class BridgeTests(unittest.TestCase):
    def serve(self, response):
        _Handler.response = response
        _Handler.requests = []
        server = HTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}/exec"

    def test_finds_github_target_from_pull_url(self):
        self.assertEqual(bridge.find_target_number("see https://github.com/atzmonpersonalassistant/trader/pull/256"), 256)

    def test_ignores_foreign_github_target_urls(self):
        self.assertIsNone(bridge.find_target_number("see https://github.com/other/repo/pull/256"))

    def test_finds_github_target_from_pr_marker(self):
        self.assertEqual(bridge.find_target_number("PR #255 needs changes"), 255)

    def test_dry_run_routes_comment_and_does_not_persist_state(self):
        url = self.serve({
            "ok": True,
            "last_row": 7,
            "messages": [{
                "row": 7,
                "created_at": "2026-09-01T18:00:00Z",
                "sender": "claude",
                "message": "PR #256: please fix the deploy check",
                "page_url": "https://example.test",
                "user_agent": "test",
            }],
        })
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "state.json"
            rc = bridge.main(["--apps-script-url", url, "--bridge-token", "secret", "--state", str(state), "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertFalse(state.exists())
        request = _Handler.requests[0]
        self.assertNotIn("secret", request["path"])
        payload = json.loads(request["body"])
        self.assertEqual(payload["token"], "secret")
        self.assertEqual(payload["after_row"], "1")

    def test_add_labels_provisions_known_missing_labels(self):
        calls = []

        def fake_request(method, url, token, payload=None):
            calls.append((method, url, payload))
            if method == "GET" and url.endswith("/labels/external:reviewer"):
                raise RuntimeError("GitHub API GET label failed with HTTP 404: not found")
            return {}

        original_request = bridge.github_request
        bridge.github_request = fake_request
        self.addCleanup(setattr, bridge, "github_request", original_request)

        bridge.add_labels("atzmonpersonalassistant", "trader", 257, ["external:reviewer"], "gh-token")

        self.assertEqual(calls[0][0], "GET")
        self.assertIn("/labels/external:reviewer", calls[0][1])
        self.assertEqual(calls[1][0], "POST")
        self.assertTrue(calls[1][1].endswith("/labels"))
        self.assertEqual(calls[1][2]["name"], "external:reviewer")
        self.assertEqual(calls[2][0], "POST")
        self.assertIn("/issues/257/labels", calls[2][1])

    def test_intake_labels_ignore_operational_label_requests(self):
        self.assertEqual(
            bridge.intake_labels("external:reviewer,agent:ready,agent:needs-fix,bug"),
            ["external:reviewer"],
        )
        self.assertEqual(bridge.intake_labels(""), ["external:reviewer"])

    def test_targeted_message_is_preserved_as_non_dispatching_intake_issue(self):
        calls = []

        def fake_exists(owner, repo, number, token):
            calls.append(("exists", number))
            return True

        def fake_request(method, url, token, payload=None):
            calls.append((method, url, payload))
            return {"number": 321}

        original_exists = bridge.github_issue_exists
        original_request = bridge.github_request
        bridge.github_issue_exists = fake_exists
        bridge.github_request = fake_request
        self.addCleanup(setattr, bridge, "github_issue_exists", original_exists)
        self.addCleanup(setattr, bridge, "github_request", original_request)

        args = type("Args", (), {
            "default_target": None,
            "labels": "external:reviewer,agent:ready",
            "dry_run": False,
            "owner": "atzmonpersonalassistant",
            "repo": "trader",
        })()
        row = {"row": 9, "message": "PR #257 please check", "created_at": "now"}
        result = bridge.process_row(args, row, "gh-token")

        self.assertEqual(result["action"], "create_issue_targeted_intake")
        self.assertEqual(result["created_issue"], 321)
        self.assertEqual(result["target_status"], "found")
        issue_calls = [call for call in calls if call[0] == "POST" and call[1].endswith("/issues")]
        self.assertEqual(len(issue_calls), 1)
        self.assertEqual(issue_calls[0][2]["labels"], ["external:reviewer"])
        self.assertIn("did not comment", issue_calls[0][2]["body"])
        urls = [call[1] for call in calls if isinstance(call, tuple) and len(call) > 1 and isinstance(call[1], str)]
        self.assertFalse(any("/issues/257/comments" in url for url in urls))
        self.assertFalse(any("/issues/257/labels" in url for url in urls))

    def test_missing_target_is_preserved_as_non_dispatching_intake_issue(self):
        calls = []

        def fake_exists(owner, repo, number, token):
            calls.append(("exists", number))
            return False

        def fake_request(method, url, token, payload=None):
            calls.append((method, url, payload))
            return {"number": 322}

        original_exists = bridge.github_issue_exists
        original_request = bridge.github_request
        bridge.github_issue_exists = fake_exists
        bridge.github_request = fake_request
        self.addCleanup(setattr, bridge, "github_issue_exists", original_exists)
        self.addCleanup(setattr, bridge, "github_request", original_request)

        args = type("Args", (), {
            "default_target": None,
            "labels": "external:reviewer,agent:ready",
            "dry_run": False,
            "owner": "atzmonpersonalassistant",
            "repo": "trader",
        })()
        row = {"row": 10, "message": "PR #999999 please check", "created_at": "now"}
        result = bridge.process_row(args, row, "gh-token")

        self.assertEqual(result["action"], "create_issue_targeted_intake")
        self.assertEqual(result["target_status"], "missing")
        issue_calls = [call for call in calls if call[0] == "POST" and call[1].endswith("/issues")]
        self.assertEqual(len(issue_calls), 1)
        self.assertEqual(issue_calls[0][2]["labels"], ["external:reviewer"])
        self.assertIn("missing", issue_calls[0][2]["body"])

    def test_default_new_issue_labels_do_not_auto_dispatch(self):
        self.assertEqual(bridge.DEFAULT_LABELS, ["external:reviewer"])

    def test_start_at_latest_initializes_state_without_routing(self):
        url = self.serve({"ok": True, "last_row": 414, "messages": []})
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "state.json"
            rc = bridge.main(["--apps-script-url", url, "--bridge-token", "secret", "--state", str(state), "--start-at-latest"])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(state.read_text())["last_row"], 414)


if __name__ == "__main__":
    unittest.main()
