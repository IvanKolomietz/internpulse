# InternPulse

**What does the tech internship market actually look like?** InternPulse ingests ~17,000 real
internship postings, cleans and normalizes them into a relational database, and serves an
interactive dashboard answering questions like:

- When do companies post Summer internships, and how fast do postings close?
- Which roles (SWE, Data Analytics, ML, QA, Quant…) have the most openings?
- Where are the jobs, who is hiring, and which roles are open to undergrads?

Data source: the community-maintained [SimplifyJobs/Summer2027-Internships](https://github.com/SimplifyJobs/Summer2027-Internships) listings feed.

## Key findings (as of Oct 2026, Summer 2027 postings)

- **Apply early.** ~28% of postings are already closed one week after going up, and about **half
  are closed by week 4–8**.
- Posting volume ramps sharply in **August** and peaks in the **first week of September**.
- Software Engineering and Data Science/ML make up roughly 70% of SWE/data-type postings;
  **QA/Test roles are scarce** (~2%), which means less competition for anyone who targets them.
- ~78% of postings are open to Bachelor's students. Only ~1.3% offer a remote option.

## Architecture

```
SimplifyJobs JSON ──► pipeline/ (Python)          ──► SQLite (normalized)  ──► server.py (JSON API) ──► static/ (React + Chart.js)
                      extract · validate · clean       listings                 /api/summary, /trend,       filters, KPIs, charts,
                      dedupe · classify · load         listing_terms            /roles, /open-rate, ...     searchable listings
                                                       listing_locations
```

| Layer | What it shows |
|---|---|
| `pipeline/transform.py` | Data cleaning: category de-duplication, regex title → role classifier, location parser (US/Canada/UK, state names, aliases like "NYC"), term normalization |
| `pipeline/ingest.py` | ETL with a data-quality report (rejected/duplicate/missing counts) and an atomic DB swap |
| `pipeline/schema.sql` | Normalized schema (1-to-many terms and locations), indexes |
| `analytics/queries.py` | SQL analytics: CTEs, conditional aggregation, date bucketing; all filters are bound parameters (SQL-injection safe) |
| `server.py` | Standard-library REST API with input validation (400s), 404s, read-only DB connections |
| `static/` | React 18 dashboard (no build step) with Chart.js; light/dark mode, responsive |
| `tests/` | 31 unit + integration tests: classifier edge cases, parser cases, known-answer fixture DB, API status codes, injection attempt |
| `.github/workflows/ci.yml` | CI matrix (Ubuntu + Windows × Python 3.11/3.12) plus a weekly live-data smoke test that catches upstream schema drift |

**Zero dependencies.** Everything runs on the Python 3.11+ standard library.

## Run it

```bash
python -m pipeline.ingest      # download + clean + load (~5s)
python server.py               # open http://localhost:8000
python -m unittest discover -s tests -t .
```

## A data-quality decision worth mentioning

My first version measured "days until a posting closes" as `date_updated - date_posted` on
closed listings. The median came out at **0.6 days**, which was implausible. Digging in showed that
`date_updated` tracks *any edit* (most land within minutes of posting), not the closing date, so the
metric was invalid. I replaced it with **share of postings still open by posting age**, which only
relies on fields that mean what they say. The reasoning is documented in `open_rate_by_age()`.

## Ideas for next steps

- Track daily snapshots to measure true time-to-close
- Skill extraction from job descriptions (TF-IDF / keyword frequency by role)
- Rewrite the API in Go for comparison; deploy to a free host

---

### Resume bullets (pick 2–3)

- Built **InternPulse**, a full-stack analytics dashboard (Python, SQL, React) that ingests and analyzes **17,000+ real internship postings** to surface hiring trends by role, location and timing
- Designed an **ETL pipeline** with validation, de-duplication and a rule-based title classifier, normalizing messy location and category fields to **99.9% parse coverage** into a normalized SQLite schema
- Wrote parameterized **SQL analytics** (CTEs, conditional aggregation, time bucketing) behind a REST API, and found that **~50% of postings close within 4–8 weeks**
- Caught and replaced an **invalid metric** after a data-quality investigation showed a timestamp field didn't mean what it appeared to
- Built a **31-test suite** (unit, integration, API, SQL-injection) and **GitHub Actions CI** across 2 OSes × 2 Python versions, plus a scheduled live-data check for upstream schema drift
