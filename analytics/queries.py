"""Analytical SQL queries over the normalized listings database.

Every query takes a `Filters` object so the dashboard can slice by term/role/etc.
All user input is passed as bound parameters, never string-formatted into SQL.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace

HOME_COUNTRY = "Canada"
# The dashboard covers North American postings only. Mexico has no postings in the source today.
COUNTRIES = ("Canada", "US")
IN_HOME = (
    "EXISTS (SELECT 1 FROM listing_locations hc WHERE hc.listing_id = {a}.id AND hc.country = '"
    + HOME_COUNTRY + "')"
)


@dataclass
class Filters:
    term: str | None = None
    roles: list[str] = field(default_factory=list)
    active_only: bool = False
    country: str | None = None
    search: str | None = None

    def where(self, alias: str = "l") -> tuple[str, list]:
        # Always limited to postings with at least one location in a covered country.
        clauses = [f"EXISTS (SELECT 1 FROM listing_locations na WHERE na.listing_id = {alias}.id"
                   f" AND na.country IN ({','.join('?' * len(COUNTRIES))}))"]
        params: list = list(COUNTRIES)
        if self.term:
            clauses.append(f"EXISTS (SELECT 1 FROM listing_terms t WHERE t.listing_id = {alias}.id AND t.term = ?)")
            params.append(self.term)
        if self.roles:
            clauses.append(f"{alias}.role IN ({','.join('?' * len(self.roles))})")
            params.extend(self.roles)
        if self.active_only:
            clauses.append(f"{alias}.active = 1")
        if self.country:
            clauses.append(f"EXISTS (SELECT 1 FROM listing_locations x WHERE x.listing_id = {alias}.id AND x.country = ?)")
            params.append(self.country)
        if self.search:
            clauses.append(f"({alias}.title LIKE ? OR {alias}.company LIKE ?)")
            params.extend([f"%{self.search}%"] * 2)
        return " AND ".join(clauses), params


def _rows(conn: sqlite3.Connection, sql: str, params: list) -> list[dict]:
    cur = conn.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def summary(conn, f: Filters) -> dict:
    w, p = f.where()
    row = _rows(conn, f"""
        SELECT COUNT(*) AS total,
               SUM(l.active) AS open,
               COUNT(DISTINCT l.company) AS companies,
               SUM(CASE WHEN l.posted >= date((SELECT MAX(posted) FROM listings), '-7 days') THEN 1 ELSE 0 END) AS last_7_days,
               MAX(l.posted) AS latest_posted
        FROM listings l WHERE {w}""", p)[0]
    remote = _rows(conn, f"""
        SELECT COUNT(DISTINCT l.id) AS n FROM listings l
        JOIN listing_locations x ON x.listing_id = l.id AND x.remote = 1
        WHERE {w}""", p)[0]["n"]
    row["remote"] = remote
    row["canada"] = conn.execute(f"SELECT COUNT(*) FROM listings l WHERE {w} AND {IN_HOME.format(a='l')}", p).fetchone()[0]
    # Of postings 4-8 weeks old, how many have already closed? (the "apply early" signal)
    aged = _rows(conn, f"""
        SELECT COUNT(*) AS n, SUM(1 - l.active) AS closed FROM listings l
        WHERE {w} AND l.posted BETWEEN date((SELECT MAX(posted) FROM listings), '-56 days')
                                   AND date((SELECT MAX(posted) FROM listings), '-28 days')""", p)[0]
    row["closed_by_week_8_pct"] = round(100 * aged["closed"] / aged["n"], 1) if aged["n"] else None
    return row


def weekly_trend(conn, f: Filters) -> list[dict]:
    """Postings per ISO week, split by role (for a stacked area chart)."""
    w, p = f.where()
    return _rows(conn, f"""
        SELECT date(l.posted, '-6 days', 'weekday 1') AS week, l.role, COUNT(*) AS n
        FROM listings l WHERE {w} AND l.posted IS NOT NULL
        GROUP BY week, l.role ORDER BY week""", p)


def role_breakdown(conn, f: Filters) -> list[dict]:
    w, p = f.where()
    return _rows(conn, f"""
        SELECT l.role, COUNT(*) AS n, SUM(l.active) AS open
        FROM listings l WHERE {w} GROUP BY l.role ORDER BY n DESC""", p)


def top_companies(conn, f: Filters, limit: int = 15) -> list[dict]:
    w, p = f.where()
    return _rows(conn, f"""
        SELECT l.company, COUNT(*) AS n, SUM(l.active) AS open,
               GROUP_CONCAT(DISTINCT l.role) AS roles
        FROM listings l WHERE {w}
        GROUP BY l.company ORDER BY n DESC, l.company LIMIT ?""", p + [limit])


def top_regions(conn, f: Filters, limit: int = 15) -> list[dict]:
    """On-site postings by state/province. With a country selected, only that country's places."""
    w, p = f.where()
    if f.country:
        in_country, extra = "AND x.country = ?", [f.country]
    else:
        in_country, extra = f"AND x.country IN ({','.join('?' * len(COUNTRIES))})", list(COUNTRIES)
    return _rows(conn, f"""
        SELECT COALESCE(x.region, x.city, x.country, 'Unknown') AS region, x.country,
               COUNT(DISTINCT l.id) AS n
        FROM listings l JOIN listing_locations x ON x.listing_id = l.id
        WHERE {w} AND x.remote = 0 {in_country}
        GROUP BY 1, 2 ORDER BY n DESC LIMIT ?""", p + extra + [limit])


def country_counts(conn, f: Filters) -> list[dict]:
    """Postings per country under every filter except country (feeds the country dropdown)."""
    w, p = replace(f, country=None).where()
    return _rows(conn, f"""
        SELECT x.country, COUNT(DISTINCT l.id) AS n
        FROM listings l JOIN listing_locations x ON x.listing_id = l.id
        WHERE {w} AND x.country IN ({','.join('?' * len(COUNTRIES))})
        GROUP BY x.country ORDER BY n DESC, x.country""", p + list(COUNTRIES))


def open_rate_by_age(conn, f: Filters) -> list[dict]:
    """Share of postings still open, bucketed by weeks since posting.

    Note: the source's date_updated tracks edits, not closure, so we can't measure
    exact time-to-close. Current open/closed status by posting age is the honest proxy.
    """
    w, p = f.where()
    return _rows(conn, f"""
        WITH aged AS (
            SELECT l.active,
                   CAST((julianday((SELECT MAX(posted) FROM listings)) - julianday(l.posted)) / 7 AS INTEGER) AS age_weeks
            FROM listings l WHERE {w} AND l.posted IS NOT NULL
        )
        SELECT MIN(age_weeks, 12) AS age_weeks, COUNT(*) AS n,
               ROUND(100.0 * SUM(active) / COUNT(*), 1) AS open_pct
        FROM aged GROUP BY 1 ORDER BY 1""", p)


def degree_requirements(conn, f: Filters) -> list[dict]:
    w, p = f.where()
    return _rows(conn, f"""
        SELECT CASE
                 WHEN l.degrees = '' THEN 'Not specified'
                 WHEN l.degrees LIKE '%Bachelor%' THEN 'Bachelor''s eligible'
                 ELSE 'Graduate only' END AS level,
               COUNT(*) AS n
        FROM listings l WHERE {w} GROUP BY level ORDER BY n DESC""", p)


def canada_overview(conn, f: Filters, limit: int = 8) -> dict:
    """Canada-only breakdowns. Ignores the country filter so the panel always shows Canada."""
    w, p = replace(f, country=HOME_COUNTRY).where()
    provinces = _rows(conn, f"""
        SELECT COALESCE(x.region, 'Remote / unspecified') AS province, COUNT(DISTINCT l.id) AS n
        FROM listings l JOIN listing_locations x ON x.listing_id = l.id AND x.country = ?
        WHERE {w} GROUP BY 1 ORDER BY n DESC""", [HOME_COUNTRY] + p)
    cities = _rows(conn, f"""
        SELECT x.city || ', ' || x.region AS city, COUNT(DISTINCT l.id) AS n
        FROM listings l JOIN listing_locations x ON x.listing_id = l.id AND x.country = ?
        WHERE {w} AND x.city IS NOT NULL AND x.region IS NOT NULL
        GROUP BY 1 ORDER BY n DESC LIMIT ?""", [HOME_COUNTRY] + p + [limit])
    companies = _rows(conn, f"""
        SELECT l.company, COUNT(*) AS n, SUM(l.active) AS open
        FROM listings l WHERE {w} GROUP BY l.company ORDER BY n DESC, l.company LIMIT ?""", p + [limit])
    total = conn.execute(f"SELECT COUNT(*) FROM listings l WHERE {w}", p).fetchone()[0]
    return {"total": total, "provinces": provinces, "cities": cities, "companies": companies}


def listings(conn, f: Filters, limit: int = 50, offset: int = 0, home_first: bool = False) -> dict:
    """Paged postings: open first, newest first; optionally postings in Canada before all others."""
    w, p = f.where()
    total = conn.execute(f"SELECT COUNT(*) FROM listings l WHERE {w}", p).fetchone()[0]
    order = f"{IN_HOME.format(a='l')} DESC, " if home_first else ""
    rows = _rows(conn, f"""
        SELECT l.id, l.company, l.title, l.role, l.active, l.posted, l.url,
               {IN_HOME.format(a='l')} AS in_canada,
               (SELECT GROUP_CONCAT(x.raw, ' | ') FROM listing_locations x WHERE x.listing_id = l.id) AS locations
        FROM listings l WHERE {w}
        ORDER BY {order}l.active DESC, l.posted DESC LIMIT ? OFFSET ?""", p + [limit, offset])
    return {"total": total, "rows": rows}


def filter_options(conn) -> dict:
    return {
        "terms": [r[0] for r in conn.execute(
            "SELECT term FROM listing_terms GROUP BY term ORDER BY COUNT(*) DESC")],
        "roles": [r[0] for r in conn.execute(
            "SELECT role FROM listings GROUP BY role ORDER BY COUNT(*) DESC")],
        "countries": list(COUNTRIES),
    }
