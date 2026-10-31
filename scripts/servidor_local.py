#!/usr/bin/env python3
"""
Servidor local para la Mac de papá.
- Sirve la UI en http://localhost:8080
- POST /trigger-scraper  → corre scraper_diario.py en background
- GET  /scraper-status   → estado actual: running / idle + resultado
"""
import json
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
FRONTEND = BASE_DIR / "frontend"
PYTHON   = BASE_DIR / "venv" / "Scripts" / "python.exe"
if not PYTHON.exists():
    PYTHON = BASE_DIR / "venv" / "bin" / "python3"
SCRAPER  = BASE_DIR / "scrapers" / "scraper_diario.py"
SECRET   = "captacion-zp-2024-secreto"
PORT     = 8080

_lock  = threading.Lock()
_state = {
    "running":    False,
    "started_at": None,   # epoch float
    "nuevas":     None,   # int | None
    "duracion":   None,   # "Xm Ys" | None
    "error":      None,   # str | None
}


def _run_scraper():
    with _lock:
        _state.update(running=True, started_at=time.time(),
                      nuevas=None, duracion=None, error=None)
    try:
        result = subprocess.run(
            [str(PYTHON), str(SCRAPER)],
            cwd=str(BASE_DIR),
            capture_output=True, text=True,
        )
        output = result.stdout + result.stderr

        nuevas = None
        duracion = None
        m = re.search(r"Nuevos insertados:\s+(\d+)", output)
        if m:
            nuevas = int(m.group(1))
        m2 = re.search(r"Tiempo total:\s+([\d]+m [\d]+s)", output)
        if m2:
            duracion = m2.group(1)

        with _lock:
            _state.update(running=False, nuevas=nuevas, duracion=duracion,
                          error=None if result.returncode == 0 else "exit " + str(result.returncode))
    except Exception as e:
        with _lock:
            _state.update(running=False, error=str(e))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/scraper-status":
            with _lock:
                snap = dict(_state)
            elapsed = None
            if snap["started_at"]:
                elapsed = int(time.time() - snap["started_at"])
            self._json(200, {**snap, "elapsed_seg": elapsed})
            return

        if path == "/":
            path = "/index.html"
        file_path = FRONTEND / path.lstrip("/")
        if not file_path.exists() or not file_path.is_file():
            self.send_response(404)
            self.end_headers()
            return
        ext = file_path.suffix.lower()
        ct = {".html": "text/html; charset=utf-8", ".js": "application/javascript",
              ".css": "text/css", ".json": "application/json",
              ".png": "image/png", ".ico": "image/x-icon"}.get(ext, "application/octet-stream")
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/trigger-scraper":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b"{}")

        if body.get("secret") != SECRET:
            self._json(403, {"ok": False, "error": "forbidden"})
            return

        with _lock:
            if _state["running"]:
                self._json(200, {"ok": False, "error": "ya esta corriendo"})
                return

        threading.Thread(target=_run_scraper, daemon=True).start()
        self._json(200, {"ok": True})


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Servidor local en http://localhost:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
