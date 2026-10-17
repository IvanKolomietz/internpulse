import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from analytics import queries as q
from pipeline.ingest import build
from server import make_server
from tests.fixtures import RAW


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = Path(cls.tmp.name) / "test.db"
        cls.report = build(RAW, cls.db)
        cls.conn = sqlite3.connect(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        cls.tmp.cleanup()

    def test_data_quality_report(self):
        self.assertEqual(self.report["raw"], 10)
        self.assertEqual(self.report["loaded"], 7)
        self.assertEqual(self.report["rejected_duplicate"], 1)
        self.assertEqual(self.report["rejected_invalid"], 2)
        self.assertEqual(self.report["missing_term"], 1)
        self.assertEqual(self.report["missing_location"], 1)

    def test_no_orphan_child_rows(self):
        orphans = self.conn.execute(
            "SELECT COUNT(*) FROM listing_locations x LEFT JOIN listings l ON l.id = x.listing_id WHERE l.id IS NULL"
        ).fetchone()[0]
        self.assertEqual(orphans, 0)

    def test_rebuild_is_idempotent(self):
        # Build twice into the same file: the second build must replace, not append.
        # (Uses its own file: Windows can't swap a DB another connection holds open.)
        path = Path(self.tmp.name) / "rebuild.db"
        build(RAW, path)
        build(RAW, path)
        conn = sqlite3.connect(path)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0], 7)
        finally:
            conn.close()

    def test_summary(self):
        s = q.summary(self.conn, q.Filters(term="Summer 2027"))
        self.assertEqual(s["total"], 4)
        self.assertEqual(s["open"], 3)
        self.assertEqual(s["companies"], 2)
        self.assertEqual(s["remote"], 1)
        self.assertEqual(s["last_7_days"], 2)
        # Postings 28-56 days old: only #4 (35d, still open) -> 0% closed.
        self.assertEqual(s["closed_by_week_8_pct"], 0.0)

    def test_role_filter(self):
        rows = q.role_breakdown(self.conn, q.Filters(roles=["QA / Test", "Quant"]))
        self.assertEqual({r["role"]: r["n"] for r in rows}, {"QA / Test": 1, "Quant": 1})

    def test_country_filter(self):
        s = q.summary(self.conn, q.Filters(country="Canada"))
        self.assertEqual(s["total"], 1)

    def test_canada_count_in_summary(self):
        self.assertEqual(q.summary(self.conn, q.Filters())["canada"], 1)  # only #4 (Toronto)

    def test_canada_overview_ignores_country_filter(self):
        ca = q.canada_overview(self.conn, q.Filters(country="US"))
        self.assertEqual(ca["total"], 1)
        self.assertEqual(ca["provinces"], [{"province": "ON", "n": 1}])
        self.assertEqual(ca["cities"], [{"city": "Toronto, ON", "n": 1}])
        self.assertEqual(ca["companies"][0]["company"], "Globex")

    def test_canada_first_sort(self):
        normal = q.listings(self.conn, q.Filters())["rows"]
        first = q.listings(self.conn, q.Filters(), home_first=True)["rows"]
        self.assertNotEqual(normal[0]["id"], "4")
        self.assertEqual(first[0]["id"], "4")
        self.assertEqual(first[0]["in_canada"], 1)
        self.assertEqual(len(first), len(normal))  # same rows, only reordered

    def test_only_north_america(self):
        # #9 (London) is in the database but never counted; #8 has no location at all.
        self.assertEqual(q.summary(self.conn, q.Filters())["total"], 5)
        ids = {r["id"] for r in q.listings(self.conn, q.Filters(), limit=50)["rows"]}
        self.assertEqual(ids, {"1", "2", "3", "4", "5"})
        self.assertEqual(q.filter_options(self.conn)["countries"], ["Canada", "US"])

    def test_country_counts_ignore_country_filter(self):
        rows = q.country_counts(self.conn, q.Filters(country="Canada"))
        self.assertEqual({r["country"]: r["n"] for r in rows}, {"US": 4, "Canada": 1})

    def test_top_regions_scoped_to_selected_country(self):
        rows = q.top_regions(self.conn, q.Filters(country="Canada"))
        self.assertEqual([r["region"] for r in rows], ["ON"])

    def test_open_rate_by_age(self):
        rows = {r["age_weeks"]: r for r in q.open_rate_by_age(self.conn, q.Filters())}
        self.assertEqual(rows[0]["n"], 2)          # #1, #2 (#8 has no location, #9 is in the UK)
        self.assertEqual(rows[0]["open_pct"], 100.0)
        self.assertEqual(rows[2]["open_pct"], 0.0)  # #3 closed at 20 days

    def test_degrees(self):
        rows = {r["level"]: r["n"] for r in q.degree_requirements(self.conn, q.Filters())}
        self.assertEqual(rows, {"Bachelor's eligible": 3, "Graduate only": 1, "Not specified": 1})

    def test_search_is_parameterized(self):
        # A classic injection string must be treated as literal text, not SQL.
        res = q.listings(self.conn, q.Filters(search="' OR 1=1 --"))
        self.assertEqual(res["total"], 0)

    def test_listings_paging_and_order(self):
        res = q.listings(self.conn, q.Filters(), limit=2, offset=0)
        self.assertEqual(res["total"], 5)
        self.assertEqual(len(res["rows"]), 2)
        self.assertTrue(all(r["active"] for r in res["rows"]))  # open postings first


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        db = Path(cls.tmp.name) / "api.db"
        build(RAW, db)
        cls.srv = make_server(0, db, quiet=True)  # port 0 = pick a free port
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=5) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_every_endpoint_returns_json(self):
        for path in ["options", "summary", "trend", "roles", "companies", "regions", "open-rate", "degrees",
                     "canada", "countries", "listings", "listings?canada_first=1"]:
            with self.subTest(path=path):
                status, body = self.get(f"/api/{path}")
                self.assertEqual(status, 200)
                self.assertIsNotNone(body)

    def test_filters_via_query_string(self):
        _, body = self.get("/api/summary?term=Summer+2027&roles=Data+Analytics&active=1")
        self.assertEqual(body["total"], 1)

    def test_unknown_endpoint_404(self):
        status, body = self.get("/api/nope")
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    def test_bad_params_400(self):
        for path in ["/api/listings?limit=abc", "/api/listings?limit=5000", "/api/listings?offset=-1",
                     "/api/summary?q=" + "x" * 101, "/api/summary?country=Germany"]:
            with self.subTest(path=path):
                status, body = self.get(path)
                self.assertEqual(status, 400)
                self.assertIn("error", body)

    def test_serves_dashboard(self):
        with urllib.request.urlopen(self.base + "/", timeout=5) as r:
            self.assertIn(b"InternPulse", r.read())


if __name__ == "__main__":
    unittest.main()
