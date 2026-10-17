"""Tiny JSON API + static file server (standard library only).

    python server.py            # http://localhost:8000
    python server.py --port 9000
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from analytics import queries as q

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DEFAULT_DB = ROOT / "data" / "internpulse.db"

ENDPOINTS = {
    "/api/summary": q.summary,
    "/api/trend": q.weekly_trend,
    "/api/roles": q.role_breakdown,
    "/api/companies": q.top_companies,
    "/api/regions": q.top_regions,
    "/api/open-rate": q.open_rate_by_age,
    "/api/degrees": q.degree_requirements,
    "/api/canada": q.canada_overview,
    "/api/countries": q.country_counts,
}


class BadRequest(ValueError):
    pass


def parse_filters(qs: dict[str, list[str]]) -> q.Filters:
    def one(key: str) -> str | None:
        v = qs.get(key, [""])[0].strip()
        return v or None

    search = one("q")
    if search and len(search) > 100:
        raise BadRequest("q too long")
    country = one("country")
    if country and country not in q.COUNTRIES:
        raise BadRequest(f"country must be one of {', '.join(q.COUNTRIES)}")
    roles = [r for r in (one("roles") or "").split(",") if r]
    return q.Filters(
        term=one("term"),
        roles=roles,
        active_only=one("active") in {"1", "true"},
        country=country,
        search=search,
    )


def int_param(qs, key: str, default: int, lo: int, hi: int) -> int:
    raw = qs.get(key, [str(default)])[0]
    try:
        v = int(raw)
    except ValueError:
        raise BadRequest(f"{key} must be an integer")
    if not lo <= v <= hi:
        raise BadRequest(f"{key} must be between {lo} and {hi}")
    return v


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, db_path: Path, **kwargs):
        self.db_path = db_path
        super().__init__(*args, directory=str(STATIC), **kwargs)

    quiet = False

    def log_message(self, fmt, *args):  # only log API calls
        if self.quiet or not self.path.startswith("/api/"):
            return
        super().log_message(fmt, *args)

    def do_GET(self):
        url = urlparse(self.path)
        if not url.path.startswith("/api/"):
            return super().do_GET()
        try:
            body = self.handle_api(url.path, parse_qs(url.query))
            self.send_json(200, body)
        except BadRequest as e:
            self.send_json(400, {"error": str(e)})
        except KeyError:
            self.send_json(404, {"error": "unknown endpoint"})

    def handle_api(self, path: str, qs: dict) -> object:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        try:
            if path == "/api/options":
                return q.filter_options(conn)
            f = parse_filters(qs)
            if path == "/api/listings":
                return q.listings(conn, f,
                                  limit=int_param(qs, "limit", 50, 1, 200),
                                  offset=int_param(qs, "offset", 0, 0, 1_000_000),
                                  home_first=qs.get("canada_first", [""])[0] in {"1", "true"})
            return ENDPOINTS[path](conn, f)
        finally:
            conn.close()

    def send_json(self, status: int, body: object) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def make_server(port: int, db_path: Path = DEFAULT_DB, quiet: bool = False) -> ThreadingHTTPServer:
    if not db_path.exists():
        raise SystemExit(f"{db_path} not found. Run: python -m pipeline.ingest")
    handler = type("BoundHandler", (Handler,), {"quiet": quiet})
    return ThreadingHTTPServer(("127.0.0.1", port), partial(handler, db_path=db_path))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = ap.parse_args()
    srv = make_server(args.port, args.db)
    print(f"InternPulse running at http://localhost:{args.port}")
    srv.serve_forever()
