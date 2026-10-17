"""Small hand-written dataset with known answers, used by integration tests."""

DAY = 86400
NOW = 1792200000  # 2026-10-16 (UTC)


def listing(id, company, title, category="Software", active=True, days_ago=0,
            terms=("Summer 2027",), locations=("Austin, TX",), degrees=("Bachelor's",)):
    return {
        "id": id, "company_name": company, "title": title, "category": category,
        "active": active, "terms": list(terms), "locations": list(locations),
        "date_posted": NOW - days_ago * DAY, "date_updated": NOW - days_ago * DAY,
        "url": f"https://example.com/{id}", "sponsorship": "Other",
        "degrees": list(degrees), "is_visible": True, "source": "test",
    }


RAW = [
    listing("1", "Acme", "Software Engineer Intern", days_ago=0),
    listing("2", "Acme", "Data Analyst Intern", category="AI/ML/Data", days_ago=3, locations=("NYC",)),
    listing("3", "Globex", "QA Automation Intern", active=False, days_ago=20, locations=("Remote in USA",)),
    listing("4", "Globex", "Quantitative Trader Intern", category="Quant", days_ago=35,
            locations=("Toronto, ON, Canada",), degrees=("Master's",)),
    listing("5", "Initech", "Machine Learning Intern", category="AI/ML/Data", active=False, days_ago=40,
            terms=("Fall 2026",), degrees=()),
    # Data-quality cases the pipeline must handle:
    listing("1", "Acme", "Duplicate of #1"),                         # duplicate id -> rejected
    {**listing("6", "Hidden Co", "SWE Intern"), "is_visible": False},  # hidden -> rejected
    listing("7", "", "No Company Intern"),                           # missing company -> rejected
    listing("8", "Umbrella", "Backend Developer Intern", terms=("N/A",), locations=()),
    # Outside North America: loaded, but excluded from every dashboard query.
    listing("9", "Hooli", "Software Engineer Intern", locations=("London, UK",)),
]
