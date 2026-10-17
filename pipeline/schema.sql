-- Normalized schema: one row per listing, with 1-to-many terms and locations.
CREATE TABLE IF NOT EXISTS listings (
    id          TEXT PRIMARY KEY,
    company     TEXT NOT NULL,
    title       TEXT NOT NULL,
    category    TEXT NOT NULL,
    role        TEXT NOT NULL,
    active      INTEGER NOT NULL CHECK (active IN (0, 1)),
    posted      TEXT,          -- ISO date
    updated     TEXT,          -- ISO date
    url         TEXT,
    sponsorship TEXT,
    degrees     TEXT           -- comma-separated
);

CREATE TABLE IF NOT EXISTS listing_terms (
    listing_id TEXT NOT NULL REFERENCES listings(id),
    term       TEXT NOT NULL,
    PRIMARY KEY (listing_id, term)
);

CREATE TABLE IF NOT EXISTS listing_locations (
    listing_id TEXT NOT NULL REFERENCES listings(id),
    raw        TEXT NOT NULL,
    city       TEXT,
    region     TEXT,
    country    TEXT,
    remote     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_listings_role    ON listings(role);
CREATE INDEX IF NOT EXISTS idx_listings_posted  ON listings(posted);
CREATE INDEX IF NOT EXISTS idx_terms_term       ON listing_terms(term);
CREATE INDEX IF NOT EXISTS idx_locations_region ON listing_locations(region);
