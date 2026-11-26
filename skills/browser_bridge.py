"""The browser tells Jarvis what's on the page: no screenshots, no clicking.

A small extension for Chrome or Edge (the browser_extension folder, loaded
once with "Load unpacked") sends the tab you're looking at to Jarvis over
localhost: its address, title, the page's readable text and what you've
selected. On request it also sends the page's code (the HTML you'd see with
Inspect element). Nothing leaves your PC.

Only the extension can post here: requests must come from a browser extension
(Origin chrome-extension://...), so a web page can't feed Jarvis fake text.
"""
import http.server
import json
import queue
import threading
import time

import config

FRESH = 30 * 60            # seconds a page report counts as "what he's looking at"
MAX_BODY = 6_000_000
_lock = threading.Lock()
_page = {}                 # the latest report from the tab in front
_html = {"url": "", "html": "", "at": 0.0}
_wants = queue.Queue()     # commands waiting for the extension ("html")
_html_ready = threading.Event()
_server = None
_last_contact = 0.0


def port() -> int:
    return int(getattr(config, "BROWSER_BRIDGE_PORT", 47321))


def connected(within: float = 120) -> bool:
    """Has the extension been in touch lately?"""
    return time.time() - _last_contact < within


def current(title_hint: str = ""):
    """The page in his browser (dict with url, title, text, selection, at), or None.
    title_hint: the browser window's title, to be sure it's the same tab."""
    with _lock:
        page = dict(_page)
    if not page or time.time() - page.get("at", 0) > FRESH:
        return None
    if title_hint:
        t = (page.get("title") or "").strip().lower()
        hint = title_hint.replace("​", "").lower()
        if t and t[:40] not in hint:
            return None
    return page


def page_code(timeout: float = 8.0):
    """The current page's HTML from the extension, or None if it didn't answer."""
    _html_ready.clear()
    _wants.put("html")
    if not _html_ready.wait(timeout):
        return None
    with _lock:
        return dict(_html)


class _Handler(http.server.BaseHTTPRequestHandler):
    def _allowed(self) -> bool:
        origin = self.headers.get("Origin", "")
        return origin.startswith(("chrome-extension://", "extension://", "moz-extension://"))

    def _send(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "*"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "*"))
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        global _last_contact
        path = self.path.partition("?")[0]
        if path == "/hello":
            return self._send({"jarvis": True})
        if not self._allowed():
            return self.send_error(403)
        _last_contact = time.time()
        if path == "/next":   # the extension waits here for a command
            try:
                want = _wants.get(timeout=20)
            except queue.Empty:
                want = ""
            return self._send({"want": want})
        self.send_error(404)

    def do_POST(self):
        global _last_contact
        if not self._allowed():
            return self.send_error(403)
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self.send_error(413)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self.send_error(400)
        _last_contact = time.time()
        path = self.path.partition("?")[0]
        if path == "/page":
            with _lock:
                _page.clear()
                _page.update(url=str(data.get("url", ""))[:2000], title=str(data.get("title", ""))[:300],
                             text=str(data.get("text", ""))[:400_000], selection=str(data.get("selection", ""))[:20_000],
                             at=time.time())
            want = ""
            try:
                want = _wants.get_nowait()
            except queue.Empty:
                pass
            return self._send({"ok": True, "want": want})
        if path == "/html":
            with _lock:
                _html.update(url=str(data.get("url", "")), html=str(data.get("html", "")), at=time.time())
            _html_ready.set()
            return self._send({"ok": True})
        self.send_error(404)

    def log_message(self, *a):
        pass


def start():
    """Listen for the extension (127.0.0.1 only)."""
    global _server
    if _server is not None or not getattr(config, "BROWSER_BRIDGE", True):
        return
    try:
        _server = http.server.ThreadingHTTPServer(("127.0.0.1", port()), _Handler)
    except OSError as e:
        print(f"[browser] couldn't listen on port {port()} for the browser extension: {e}")
        return
    threading.Thread(target=_server.serve_forever, daemon=True, name="browser-bridge").start()
