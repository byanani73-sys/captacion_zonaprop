#!/usr/bin/env python3
"""
Servidor local para la Mac de papá.
- Sirve la UI en http://localhost:8080
- POST /trigger-scraper  → corre scraper_diario.py en background
"""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

BASE_DIR  = Path(__file__).parent.parent
FRONTEND  = BASE_DIR / "frontend"
PYTHON    = BASE_DIR / "venv" / "bin" / "python3"
SCRAPER   = BASE_DIR / "scrapers" / "scraper_diario.py"
SECRET    = "captacion-zp-2024-secreto"
PORT      = 8080

scraper_lock = threading.Lock()
scraper_running = False


def run_scraper():
    global scraper_running
    try:
        subprocess.run([str(PYTHON), str(SCRAPER)], cwd=str(BASE_DIR), check=False)
    finally:
        with scraper_lock:
            scraper_running = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silenciar logs de acceso

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path != "/trigger-scraper":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b"{}")

        if body.get("secret") != SECRET:
            self.send_response(403)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":false,"error":"forbidden"}')
            return

        global scraper_running
        with scraper_lock:
            if scraper_running:
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":false,"error":"ya esta corriendo"}')
                return
            scraper_running = True
            threading.Thread(target=run_scraper, daemon=True).start()

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            path = "/index.html"
        file_path = FRONTEND / path.lstrip("/")

        if not file_path.exists() or not file_path.is_file():
            self.send_response(404)
            self.end_headers()
            return

        ext = file_path.suffix.lower()
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".js":   "application/javascript",
            ".css":  "text/css",
            ".json": "application/json",
            ".png":  "image/png",
            ".ico":  "image/x-icon",
        }
        ct = content_types.get(ext, "application/octet-stream")
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Servidor local en http://localhost:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
