"""AudioTrimmer web server: serves the browser UI, streams audio, computes
peaks and exports MP3 via pydub. Pure stdlib (no extra dependencies)."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydub import AudioSegment  # noqa: E402
from audiotrimmer.audio import export_mp3  # noqa: E402
from audiotrimmer.config import load as load_config, save as save_config  # noqa: E402

STATIC = ROOT / "web"
PORT = 8001


class Handler(BaseHTTPRequestHandler):
    server_version = "AudioTrimmerWeb/1.0"

    def log_message(self, fmt, *args):  # silence request log
        pass

    # ---- helpers ---------------------------------------------------------

    def _send_bytes(self, data: bytes, ctype: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj, status: int = 200):
        self._send_bytes(json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json", status)

    def _read_json(self, size: int = 5 * 1024 * 1024) -> dict:
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        return json.loads(raw.decode("utf-8"))

    def _send_static(self, name: str):
        p = STATIC / name
        if not p.is_file():
            return self._send_bytes(b"not found", "text/plain", 404)
        self._send_bytes(p.read_bytes(), mimetypes.guess_type(name)[0] or "application/octet-stream")

    # ---- routes -----------------------------------------------------------

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self._send_static("index.html")
        if path in ("/style.css", "/app.js", "/favicon.ico"):
            return self._send_static(path[1:])
        if path == "/api/settings":
            return self._send_json(load_config())
        return self._send_bytes(b"not found", "text/plain", 404)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/settings":
            body = self._read_json()
            cfg = load_config()
            for key in ("source", "output"):
                if body.get(key):
                    val = Path(str(body[key]).strip())
                    try:
                        val.mkdir(parents=True, exist_ok=True)
                        cfg[key] = str(val)
                    except OSError as exc:
                        return self._send_json({"ok": False, "error": str(exc)}, 400)
            save_config(cfg)
            return self._send_json({"ok": True, **cfg})
        if path == "/api/export-upload":
            return self._handle_export_upload()
        return self._send_bytes(b"not found", "text/plain", 404)

    def _handle_export_upload(self):
        ctype = self.headers.get("Content-Type", "")
        if not ctype.startswith("multipart/form-data"):
            return self._send_json({"ok": False, "error": "expected multipart/form-data"}, 400)
        boundary = None
        for part in ctype.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part[len("boundary="):].strip('"').encode()
        if not boundary:
            return self._send_json({"ok": False, "error": "missing boundary"}, 400)
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        fields = {}
        for chunk in raw.split(b"--" + boundary):
            if not chunk or chunk in (b"\r\n", b"--\r\n", b"--"):
                continue
            head, _, body = chunk.partition(b"\r\n\r\n")
            body = body.rstrip(b"\r\n")
            disp = ""
            for line in head.split(b"\r\n"):
                if line.lower().startswith(b"content-disposition:"):
                    disp = line.decode("utf-8", "replace")
                    break
            name, filename = "", None
            for token in disp.split(";"):
                token = token.strip()
                if token.startswith("name="):
                    name = token[len("name="):].strip('"')
                elif token.startswith("filename="):
                    filename = token[len("filename="):].strip('"')
            if filename is not None:
                fields["_file"] = (filename, body)
            else:
                fields[name] = body.decode("utf-8", "replace")
        file_data = fields.get("_file")
        if not file_data:
            return self._send_json({"ok": False, "error": "no file uploaded"}, 400)
        filename, data = file_data
        start = int(float(fields.get("start", 0)))
        end = int(float(fields.get("end", 0)))
        bitrate = fields.get("bitrate", "192k")
        if end <= start:
            return self._send_json({"ok": False, "error": "bad range"}, 400)
        tmp = ROOT / ".uploadtmp"
        tmp.mkdir(exist_ok=True)
        ext = Path(filename).suffix or ".m4a"
        tmp_path = tmp / f"upload{ext}"
        tmp_path.write_bytes(data)
        try:
            cfg = load_config()
            seg = AudioSegment.from_file(str(tmp_path))
            stem = Path(filename).stem
            out_dir = Path(cfg.get("output", ""))
            out_dir.mkdir(parents=True, exist_ok=True)
            out_name = f"{stem}_trim_{start}-{end}ms.mp3"
            out_path = out_dir / out_name
            export_mp3(seg, start, end, out_path, bitrate)
            return self._send_json({"ok": True, "file": out_name, "path": str(out_path)})
        except Exception as exc:  # noqa: BLE001
            return self._send_json({"ok": False, "error": str(exc)}, 500)
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://localhost:{args.port}"
    print(f"[*] AudioTrimmer web at {url}")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()