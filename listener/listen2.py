#!/usr/bin/env python3
"""
Script Editor Web App (listen2)
Takes a .script file and opens a web page for running that script.

Serves a code editor that displays the script, tracks the current word, and
executes bracketed commands by posting them directly to the interpreter
iframes it embeds (no separate relay process).
"""

import argparse
import json
import mimetypes
import sys
import threading
import time
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

EDITOR_DIR = Path(__file__).parent / "listen2"
EDITOR_HTML = EDITOR_DIR / "editor.html"
API_DOCS_HTML = EDITOR_DIR / "api-docs.html"
# Interpreter pages (browser_2d.html, browser_3d.html, colors.js, ...) are
# served so the editor can embed them as iframes.
INTERPRETERS_DIR = (Path(__file__).parent.parent / "interpreters" / "browser").resolve()
DEFAULT_PORT = 8100


class EditorHandler(BaseHTTPRequestHandler):
    """Serves the editor page and the script contents."""

    def __init__(self, *args, script_path=None, **kwargs):
        self.script_path = script_path
        super().__init__(*args, **kwargs)

    def _send(self, status, content, content_type):
        body = content.encode("utf-8") if isinstance(content, str) else content
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/editor.html"):
            self._send(200, EDITOR_HTML.read_text(encoding="utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api-docs.html":
            self._send(200, API_DOCS_HTML.read_text(encoding="utf-8"), "text/html; charset=utf-8")
        elif self.path == "/script":
            content = self.script_path.read_text(encoding="utf-8")
            payload = json.dumps({"path": str(self.script_path), "content": content})
            self._send(200, payload, "application/json")
        elif self.path == "/events":
            self._stream_events()
        elif self.path.startswith("/interpreters/"):
            self._serve_interpreter_file(self.path[len("/interpreters/"):])
        else:
            self._send(404, "Not found", "text/plain; charset=utf-8")

    def _serve_interpreter_file(self, rel_path):
        """Serve a file from the interpreters/browser directory (for iframes)."""
        target = (INTERPRETERS_DIR / rel_path).resolve()
        # Guard against path traversal outside the interpreters directory.
        if INTERPRETERS_DIR not in target.parents or not target.is_file():
            self._send(404, "Not found", "text/plain; charset=utf-8")
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self._send(200, target.read_bytes(), content_type)

    def _stream_events(self):
        """Server-Sent Events stream: push the script contents whenever the
        file's modification time changes. The connection stays open, so this
        relies on the server being threaded."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        last_mtime = None
        try:
            while True:
                try:
                    mtime = self.script_path.stat().st_mtime
                except OSError:
                    # File temporarily missing (e.g. mid-save); try again shortly.
                    time.sleep(0.3)
                    continue

                if mtime != last_mtime:
                    last_mtime = mtime
                    content = self.script_path.read_text(encoding="utf-8")
                    payload = json.dumps({"path": str(self.script_path), "content": content})
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    self.wfile.write(b": keep-alive\n\n")  # flush hint / heartbeat
                    self.wfile.flush()

                time.sleep(0.3)
        except (BrokenPipeError, ConnectionResetError):
            # Browser closed the tab / reloaded; end the stream quietly.
            return

    def log_message(self, *args):
        # Quiet the default per-request logging.
        pass


def main():
    parser = argparse.ArgumentParser(description="Open a web editor for a .script file")
    parser.add_argument("script", help="Path to .script file")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port to serve on (default: {DEFAULT_PORT})")
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open the browser")
    args = parser.parse_args()

    script_path = Path(args.script).expanduser().resolve()
    if not script_path.is_file():
        print(f"Error: script file not found: {script_path}")
        sys.exit(1)

    handler = partial(EditorHandler, script_path=script_path)
    server = ThreadingHTTPServer(("localhost", args.port), handler)
    url = f"http://localhost:{args.port}/"

    print("=" * 60)
    print("SCRIPT EDITOR")
    print("=" * 60)
    print(f"Script: {script_path}")
    print(f"Serving at: {url}")
    print("Press Ctrl+C to stop.")
    print("=" * 60)

    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
