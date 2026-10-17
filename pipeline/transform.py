"""Pure cleaning/normalization functions for raw internship listings.

Every function here is side-effect free so it can be unit tested in isolation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC", "PR",
}
US_STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI",
    "wyoming": "WY", "district of columbia": "DC", "washington dc": "DC", "washington, dc": "DC",
}
CA_PROVINCES = {"ON", "QC", "BC", "AB", "MB", "SK", "NS", "NB", "NL", "PE", "NT", "YT", "NU"}
US_ALIASES = {"usa", "us", "united states", "united states of america", "u.s."}
CA_PROVINCE_NAMES = {
    "ontario": "ON", "quebec": "QC", "québec": "QC", "british columbia": "BC", "alberta": "AB",
    "manitoba": "MB", "saskatchewan": "SK", "nova scotia": "NS", "new brunswick": "NB",
    "newfoundland and labrador": "NL", "prince edward island": "PE",
}
# Nicknames and well-known cities that often appear without a region: name -> (city, region, country)
CITY_ALIASES = {
    "nyc": ("New York", "NY", "US"),
    "new york city": ("New York", "NY", "US"),
    "sf": ("San Francisco", "CA", "US"),
    "south sf": ("South San Francisco", "CA", "US"),
    "bay area": ("San Francisco", "CA", "US"),
    "toronto": ("Toronto", "ON", "Canada"),
    "gta": ("Toronto", "ON", "Canada"),
    "mississauga": ("Mississauga", "ON", "Canada"),
    "ottawa": ("Ottawa", "ON", "Canada"),
    "vancouver": ("Vancouver", "BC", "Canada"),
    "montreal": ("Montreal", "QC", "Canada"),
    "montréal": ("Montreal", "QC", "Canada"),
    "calgary": ("Calgary", "AB", "Canada"),
    "edmonton": ("Edmonton", "AB", "Canada"),
}

# Raw categories drift over time ("Software" vs "Software Engineering"); collapse them.
CATEGORY_MAP = {
    "software": "Software",
    "software engineering": "Software",
    "ai/ml/data": "AI/ML/Data",
    "data science, ai & machine learning": "AI/ML/Data",
    "hardware": "Hardware",
    "hardware engineering": "Hardware",
    "product": "Product",
    "product management": "Product",
    "quant": "Quant",
    "quantitative finance": "Quant",
}

# Ordered: first match wins. Patterns run against the lower-cased title.
ROLE_RULES: list[tuple[str, re.Pattern]] = [
    ("Quant", re.compile(r"\bquant|\btrad(er|ing)\b|\bstrateg(ist|y) intern")),
    ("QA / Test", re.compile(r"\bqa\b|quality assurance|\bsdet\b|\btest(ing|er)?\b|\bautomation engineer")),
    ("Data Engineering", re.compile(r"data engineer|\betl\b|data platform|data infrastructure")),
    ("Data Analytics", re.compile(r"analyst|analytics|business intelligence|\bbi\b|insights|reporting")),
    ("Data Science / ML", re.compile(r"data scien|machine learning|\bml\b|\bai\b|deep learning|computer vision|\bnlp\b|research scien|\bllm")),
    ("Software Engineering", re.compile(r"software|developer|\bswe\b|back[- ]?end|front[- ]?end|full[- ]?stack|mobile|\bios\b|android|devops|\bsre\b|site reliability|cloud|security|platform|web")),
    ("Hardware", re.compile(r"hardware|electrical|firmware|embedded|asic|fpga|silicon|circuit|rf\b|mechanical")),
    ("Product", re.compile(r"product manag|\bpm\b|program manag|product design|\bux\b|\bui\b")),
]
CATEGORY_FALLBACK_ROLE = {
    "Software": "Software Engineering",
    "AI/ML/Data": "Data Science / ML",
    "Hardware": "Hardware",
    "Product": "Product",
    "Quant": "Quant",
}

TERM_RE = re.compile(r"^(Spring|Summer|Fall|Winter)\s+(\d{4})$", re.I)


@dataclass(frozen=True)
class Location:
    raw: str
    city: str | None
    region: str | None
    country: str | None
    remote: bool


def normalize_category(raw: str | None) -> str:
    if not raw:
        return "Other"
    return CATEGORY_MAP.get(raw.strip().lower(), "Other")


def classify_role(title: str, category: str) -> str:
    """Map a free-text job title to a role family; fall back to the category."""
    t = (title or "").lower()
    for role, pattern in ROLE_RULES:
        if pattern.search(t):
            return role
    return CATEGORY_FALLBACK_ROLE.get(category, "Other")


def parse_location(raw: str) -> Location:
    """Parse strings like 'Santa Clara, CA', 'Remote in USA', 'Toronto, ON, Canada', 'NYC'."""
    s = (raw or "").strip()
    low = s.lower()
    remote = "remote" in low
    rest = re.sub(r"\bremote\b( in)?", "", s, flags=re.I).strip(" ,-()")

    if not rest:
        return Location(s, None, None, "US" if remote and "us" in low else None, remote)

    alias = CITY_ALIASES.get(rest.lower())
    if alias:
        return Location(s, *alias, remote)
    if rest.lower() in US_ALIASES:
        return Location(s, None, None, "US", remote)

    parts = [p.strip() for p in rest.split(",") if p.strip()]
    city = parts[0] if len(parts) > 1 else None
    region = country = None
    tail = [p.upper() for p in parts[1:]] if len(parts) > 1 else [parts[0].upper()]

    for token in tail:
        low_tok = token.lower()
        if low_tok in CITY_ALIASES:
            alias_city, region, country = CITY_ALIASES[low_tok]
            city = city or alias_city
        elif low_tok in CA_PROVINCE_NAMES:
            region, country = CA_PROVINCE_NAMES[low_tok], "Canada"
        elif low_tok in US_STATE_NAMES:
            region, country = US_STATE_NAMES[low_tok], "US"
        elif token in US_STATES:
            region, country = token, "US"
        elif token in CA_PROVINCES:
            region, country = token, "Canada"
        elif token.lower() in US_ALIASES:
            country = "US"
        elif token in {"CANADA"}:
            country = "Canada"
        elif token in {"UK", "UNITED KINGDOM", "ENGLAND"}:
            country = "UK"
        else:
            country = country or token.title()

    # "Ontario, Canada" / "Texas, USA": the first part is a region, not a city.
    if city and region is None:
        if city.lower() in CA_PROVINCE_NAMES:
            region, city = CA_PROVINCE_NAMES[city.lower()], None
            country = country or "Canada"
        elif city.lower() in US_STATE_NAMES:
            region, city = US_STATE_NAMES[city.lower()], None
            country = country or "US"

    if len(parts) == 1 and country and country not in {"US", "Canada", "UK"} and region is None:
        # Single token that isn't a known place code: treat it as a city of unknown country.
        city, country = parts[0], None
    return Location(s, city, region, country, remote)


def normalize_terms(terms: list[str] | None) -> list[str]:
    """Keep only well-formed 'Season YYYY' terms, title-cased and de-duplicated."""
    out: list[str] = []
    for t in terms or []:
        m = TERM_RE.match((t or "").strip())
        if m:
            term = f"{m.group(1).title()} {m.group(2)}"
            if term not in out:
                out.append(term)
    return out


def to_iso_date(epoch: int | float | None) -> str | None:
    if not epoch:
        return None
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).date().isoformat()


def clean_listing(raw: dict) -> dict | None:
    """Turn one raw record into a clean row, or None if it is unusable."""
    if not raw.get("id") or not raw.get("title") or not raw.get("company_name"):
        return None
    if raw.get("is_visible") is False:
        return None
    category = normalize_category(raw.get("category"))
    title = " ".join(raw["title"].split())
    active = bool(raw.get("active"))
    return {
        "id": raw["id"],
        "company": raw["company_name"].strip(),
        "title": title,
        "category": category,
        "role": classify_role(title, category),
        "active": active,
        "posted": to_iso_date(raw.get("date_posted")),
        "updated": to_iso_date(raw.get("date_updated")),
        "url": raw.get("url"),
        "sponsorship": raw.get("sponsorship") or "Other",
        "terms": normalize_terms(raw.get("terms")),
        "degrees": sorted(set(raw.get("degrees") or [])),
        "locations": [parse_location(l) for l in raw.get("locations") or [] if l and l.strip()],
    }
