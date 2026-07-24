"""
app.py -- Local dashboard server for the US Equity Entry-Timing app.

Run:   python app.py
Then open http://127.0.0.1:8765  (a browser tab opens automatically).

Uses only the Python standard library for the web layer, so there is no
heavy web-framework install. Data fetching lives in market_data.py.
"""

from __future__ import annotations

import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import market_data

HOST = "127.0.0.1"
PORT = 8765
HERE = os.path.dirname(os.path.abspath(__file__))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence default logging noise
        pass

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "dashboard.html"), "r", encoding="utf-8") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
            return

        if path == "/api/data":
            if "refresh=1" in self.path:
                market_data.clear_cache()
            try:
                report = market_data.build_report()
                self._send(200, json.dumps(report), "application/json")
            except Exception as e:  # noqa: BLE001
                self._send(500, json.dumps({"error": str(e)}), "application/json")
            return

        self._send(404, "Not found", "text/plain")


def main():
    url = f"http://{HOST}:{PORT}"
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("=" * 58)
    print("  US Equity Entry-Timing Dashboard")
    print(f"  Serving at  {url}")
    print("  Press Ctrl+C to stop.")
    print("=" * 58)
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
