# InternPulse

**What does the North American tech internship market actually look like?** InternPulse ingests ~17,000 real
internship postings, focuses on the ~16,000 in Canada and the US, cleans and normalizes them into a relational database, and serves an
interactive dashboard answering questions like:

- When do companies post Summer internships, and how fast do postings close?
- Which roles (SWE, Data Analytics, ML, QA, Quant…) have the most openings?
- Where are the jobs, who is hiring, and which roles are open to undergrads?

It covers **Canada and the US**, with a **Canada focus**: a Canada panel (postings by province and city, and who is hiring there), a Canada KPI, Canadian provinces highlighted on the location chart, and a "Canada first" sort for the listings.

Data source: the community-maintained [SimplifyJobs/Summer2027-Internships](https://github.com/SimplifyJobs/Summer2027-Internships) listings feed.

## Key findings (as of Oct 2026, Summer 2027 postings)

- **Apply early.** ~28% of postings are already closed one week after going up, and about **half
  are closed by week 4–8**.
- Posting volume ramps sharply in **August** and peaks in the **first week of September**.
- Software Engineering and Data Science/ML make up roughly 70% of SWE/data-type postings;
  **QA/Test roles are scarce** (~2%), which means less competition for anyone who targets them.
- Only ~4% of Summer 2027 postings in this source are in Canada (Ontario has about two-thirds of them), so Canadian students should also watch company career pages directly.
- ~78% of postings are open to Bachelor's students. Only ~1.3% offer a remote option.

## Architecture

```
SimplifyJobs JSON ──► pipeline/ (Python)          ──► SQLite (normalized)  ──► server.py (JSON API) ──► static/ (React + Chart.js)
                      extract · validate · clean       listings                 /api/summary, /trend,       filters, KPIs, charts,
                      dedupe · classify · load         listing_terms            /canada, /open-rate, ...     searchable listings
                                                       listing_locations
```

| Layer | What it shows |
|---|---|
| `pipeline/transform.py` | Data cleaning: category de-duplication, regex title → role classifier, location parser (US/Canada/UK, state and province names, aliases like "NYC" and "Toronto"), term normalization |
| `pipeline/ingest.py` | ETL with a data-quality report (rejected/duplicate/missing counts) and an atomic DB swap |
| `pipeline/schema.sql` | Normalized schema (1-to-many terms and locations), indexes |
| `analytics/queries.py` | SQL analytics: CTEs, conditional aggregation, date bucketing; all filters are bound parameters (SQL-injection safe) |
| `server.py` | Standard-library REST API with input validation (400s), 404s, read-only DB connections |
| `static/` | React 18 dashboard (no build step) with Chart.js; light/dark mode, responsive |
| `tests/` | 41 unit + integration tests: classifier edge cases, parser cases, known-answer fixture DB, API status codes, injection attempt |
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

## How this was built

Built with [Claude Code](https://claude.com/claude-code), Anthropic's AI coding agent. I set the goal
(a data project for the roles I'm targeting) and chose the project direction and stack; Claude Code
wrote the code and tests, and checked its own metrics against the raw data, which is how the invalid
"days open" metric above was caught.
