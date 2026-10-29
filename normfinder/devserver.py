"""Lokaler Testserver, der sich wie die Caddy-Konfiguration verhält:
/normfinder/bgb/573 → bgb/573.html, /normfinder/bgb/ → bgb/index.html, sonst 404.html."""
from __future__ import annotations

import http.server
import posixpath
import urllib.parse
from functools import partial
from pathlib import Path


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, root: Path, base: str, **kw):
        self.site_root = root
        self.base = base
        super().__init__(*args, directory=str(root), **kw)

    def log_message(self, fmt, *args):  # ruhig
        pass

    def resolve(self, path: str) -> Path | None:
        path = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
        if not path.startswith(self.base):
            return None
        rel = posixpath.normpath(path[len(self.base):]).lstrip("/")
        if rel in (".", ""):
            rel = ""
        cand = [rel, rel + ".html", posixpath.join(rel, "index.html")]
        for c in cand:
            p = (self.site_root / c).resolve()
            if str(p).startswith(str(self.site_root.resolve())) and p.is_file():
                return p
        return None

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path).path
        if url == self.base.rstrip("/"):
            self.send_response(308)
            self.send_header("Location", self.base)
            self.end_headers()
            return
        p = self.resolve(self.path)
        status = 200
        if p is None:
            p = self.site_root / "404.html"
            status = 404
        ctype = self.guess_type(str(p))
        if ctype.startswith("text/") or ctype in ("application/json", "application/javascript"):
            ctype += "; charset=utf-8"
        data = p.read_bytes()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                         "object-src 'none'; base-uri 'none'; frame-ancestors 'self'; form-action 'self'")
        self.end_headers()
        self.wfile.write(data)


def serve(root: Path, port: int, base: str = "/normfinder/"):
    root = root.resolve()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, root=root, base=base))
    print(f"Normfinder läuft auf http://127.0.0.1:{port}{base}  (Strg+C beendet)")
    httpd.serve_forever()
