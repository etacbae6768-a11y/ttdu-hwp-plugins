import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class MockService:
    """A tiny stand-in for the hub API / local runner. Set .reply = (status, json_body, headers)."""

    def __init__(self):
        self.reply = (200, {"ok": True}, {})
        self.calls = []
        svc = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _go(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                svc.calls.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
                status, js, hdrs = svc.reply(self.path) if callable(svc.reply) else svc.reply
                raw = json.dumps(js).encode() if not isinstance(js, bytes) else js
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                for k, v in (hdrs or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            do_POST = _go
            do_GET = _go

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()


@pytest.fixture
def svc():
    s = MockService()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ["TTDU_HWP_BACKEND", "TTDU_API_KEY", "TTDU_HUB_URL", "TTDU_LOCAL_URL", "TTDU_LOCAL_KEY", "TTDU_LOCAL_KEY_FILE", "TTDU_HWP_TIMEOUT"]:
        monkeypatch.delenv(k, raising=False)
