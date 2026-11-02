#!/usr/bin/env python3
"""Serve a wall display and a JSON snapshot using only the standard library."""

import argparse
from datetime import datetime
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent


def validate_data(data):
    """Reject incomplete snapshots instead of mistaking missing data for empty lists."""
    if not isinstance(data, dict):
        raise ValueError("Expected an object")
    for key, kind in {"at": str, "now": (int, float), "head": dict,
                      "decisions": list, "hands": list, "notices": list,
                      "schedule": list, "requests": list, "teams": list,
                      "money": (str, type(None))}.items():
        if key not in data or not isinstance(data[key], kind):
            raise ValueError("Invalid snapshot")
    for key in ("members", "working"):
        if type(data["head"].get(key)) is not int or data["head"][key] < 0:
            raise ValueError("Invalid head count")
    if type(data["now"]) not in (int, float) or not math.isfinite(data["now"]):
        raise ValueError("Invalid snapshot time")
    fields = {"decisions": {"id": str, "what": str},
              "hands": {"id": str, "title": str, "when": str},
              "notices": {"id": str, "title": str},
              "schedule": {"id": str, "time": str, "title": str},
              "requests": {"id": str, "fromId": str, "toId": str,
                           "title": str, "stage": str, "t": (int, float)},
              "teams": {"name": str, "task": str, "worker": str}}
    for section, required in fields.items():
        seen = set()
        for item in data[section]:
            if not isinstance(item, dict) or any(
                key not in item or not isinstance(item[key], kind)
                for key, kind in required.items()
            ):
                raise ValueError("Invalid row")
            identity = item["name" if section == "teams" else "id"]
            if not identity or identity in seen:
                raise ValueError("Row identities must be unique")
            seen.add(identity)
            for key in ("by", "stops", "extra", "original", "updated", "work_id"):
                if key in item and not isinstance(item[key], str):
                    raise ValueError("Invalid text")
            for key in ("blocked", "done"):
                if key in item and type(item[key]) is not bool:
                    raise ValueError("Invalid flag")
            if "more" in item and (type(item["more"]) is not int or item["more"] < 0):
                raise ValueError("Invalid additional count")
            if "ids" in item and (not isinstance(item["ids"], list)
                                  or any(not isinstance(s, str) for s in item["ids"])):
                raise ValueError("Invalid member list")
            if section == "requests" and (type(item["t"]) not in (int, float)
                                           or not math.isfinite(item["t"])):
                raise ValueError("Invalid request time")
    return data


def read_data(path):
    def reject_constant(_):
        raise ValueError("Non-finite number")
    return validate_data(json.loads(path.read_text(encoding="utf-8"),
                                    parse_constant=reject_constant))


def json_bytes(data):
    return json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, data_path, **kwargs):
        self.data_path = data_path
        super().__init__(*args, **kwargs)

    def reply(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; "
                         "script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                         "connect-src 'self'; img-src 'self'; base-uri 'none'; "
                         "frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def json_reply(self, data):
        self.reply(200, json_bytes(data), "application/json; charset=utf-8")

    def do_GET(self):
        route = urlsplit(self.path).path
        if route in ("/", "/pad", "/pad/"):
            self.reply(200, (ROOT / "pad.html").read_bytes(), "text/html; charset=utf-8")
        elif route == "/pad.json":
            try:
                body = json_bytes(read_data(self.data_path))
            except (OSError, ValueError, TypeError, RecursionError, OverflowError):
                body = json_bytes({"error": "data_unavailable",
                                   "at": datetime.now().strftime("%H:%M")})
            self.reply(200, body, "application/json; charset=utf-8")
        elif route == "/favicon.ico":
            self.reply(204, b"", "image/x-icon")
        elif route == "/healthz":
            self.json_reply({"ok": True})
        else:
            self.reply(404, b"Not found\n", "text/plain; charset=utf-8")

    def log_message(self, format, *args):
        pass


def make_server(data_path, host="127.0.0.1", port=8792):
    return ThreadingHTTPServer((host, port), partial(Handler, data_path=Path(data_path)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "demo" / "demo.json")
    parser.add_argument("--port", type=int, default=8792)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    with make_server(args.data, args.host, args.port) as server:
        print(f"Wallboard: http://{args.host}:{server.server_port}/pad", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
