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

    def do_GET(self):
        self.__class__.requests.append(self.path)
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
        self.assertIn("token=secret", _Handler.requests[0])
        self.assertIn("after_row=1", _Handler.requests[0])

    def test_start_at_latest_initializes_state_without_routing(self):
        url = self.serve({"ok": True, "last_row": 414, "messages": []})
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "state.json"
            rc = bridge.main(["--apps-script-url", url, "--bridge-token", "secret", "--state", str(state), "--start-at-latest"])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(state.read_text())["last_row"], 414)


if __name__ == "__main__":
    unittest.main()
