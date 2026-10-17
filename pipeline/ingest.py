"""Extract -> clean -> load raw listings into a normalized SQLite database.

Usage:
    python -m pipeline.ingest                 # download latest data
    python -m pipeline.ingest --file raw.json # use a local copy
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import urllib.request
from collections import Counter
from pathlib import Path

from .transform import clean_listing

SOURCE_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/"
    "dev/.github/scripts/listings.json"
)
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "internpulse.db"
SCHEMA = (Path(__file__).parent / "schema.sql").read_text()


def fetch(url: str = SOURCE_URL) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "internpulse/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def load(raw_rows: list[dict], conn: sqlite3.Connection) -> dict:
    """Clean and insert rows. Returns a data-quality report."""
    conn.executescript(SCHEMA)
    report = Counter(raw=len(raw_rows))
    seen: set[str] = set()

    for raw in raw_rows:
        row = clean_listing(raw)
        if row is None:
            report["rejected_invalid"] += 1
            continue
        if row["id"] in seen:
            report["rejected_duplicate"] += 1
            continue
        seen.add(row["id"])
        if not row["terms"]:
            report["missing_term"] += 1
        if not row["locations"]:
            report["missing_location"] += 1

        conn.execute(
            "INSERT INTO listings (id, company, title, category, role, active, posted, updated,"
            " url, sponsorship, degrees) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (row["id"], row["company"], row["title"], row["category"], row["role"],
             int(row["active"]), row["posted"], row["updated"],
             row["url"], row["sponsorship"], ",".join(row["degrees"])),
        )
        conn.executemany(
            "INSERT INTO listing_terms (listing_id, term) VALUES (?, ?)",
            [(row["id"], t) for t in row["terms"]],
        )
        conn.executemany(
            "INSERT INTO listing_locations (listing_id, raw, city, region, country, remote)"
            " VALUES (?,?,?,?,?,?)",
            [(row["id"], l.raw, l.city, l.region, l.country, int(l.remote)) for l in row["locations"]],
        )
        report["loaded"] += 1

    conn.commit()
    return dict(report)


def build(raw_rows: list[dict], db_path: Path) -> dict:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp)
    try:
        report = load(raw_rows, conn)
    finally:
        conn.close()
    tmp.replace(db_path)  # atomic swap so the API never reads a half-built DB
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", type=Path, help="local listings.json instead of downloading")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = ap.parse_args()

    raw = json.loads(args.file.read_text(encoding="utf-8")) if args.file else fetch()
    report = build(raw, args.db)
    print(f"Built {args.db}")
    for k, v in report.items():
        print(f"  {k:>20}: {v:,}")


if __name__ == "__main__":
    main()
