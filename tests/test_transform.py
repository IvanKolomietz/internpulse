import unittest

from pipeline.transform import (
    classify_role, clean_listing, normalize_category, normalize_terms, parse_location,
)


class NormalizeCategoryTest(unittest.TestCase):
    def test_collapses_synonyms(self):
        self.assertEqual(normalize_category("Software Engineering"), "Software")
        self.assertEqual(normalize_category("software"), "Software")
        self.assertEqual(normalize_category("Data Science, AI & Machine Learning"), "AI/ML/Data")
        self.assertEqual(normalize_category("Quantitative Finance"), "Quant")

    def test_unknown_or_missing_is_other(self):
        self.assertEqual(normalize_category("Basket Weaving"), "Other")
        self.assertEqual(normalize_category(None), "Other")
        self.assertEqual(normalize_category(""), "Other")


class ClassifyRoleTest(unittest.TestCase):
    def check(self, title, expected, category="Other"):
        with self.subTest(title=title):
            self.assertEqual(classify_role(title, category), expected)

    def test_title_rules(self):
        self.check("Software Engineer Intern", "Software Engineering")
        self.check("Backend Developer Intern - Summer 2027", "Software Engineering")
        self.check("Data Analyst Intern", "Data Analytics")
        self.check("Business Intelligence Intern", "Data Analytics")
        self.check("QA Automation Intern", "QA / Test")
        self.check("Software Test Engineer Intern", "QA / Test")
        self.check("SDET Intern", "QA / Test")
        self.check("Quantitative Researcher Intern", "Quant")
        self.check("Machine Learning Engineer Intern", "Data Science / ML")
        self.check("Data Engineer Intern", "Data Engineering")
        self.check("Firmware Engineer Intern", "Hardware")

    def test_rule_order_prefers_more_specific_role(self):
        # "Quantitative Analyst" must be Quant, not Data Analytics.
        self.check("Quantitative Analyst Intern", "Quant")
        # A test role on a software team is QA, not generic SWE.
        self.check("Software QA Intern", "QA / Test")

    def test_word_boundaries_avoid_false_positives(self):
        # "contest" / "latest" contain "test" but are not QA roles.
        self.check("Contest Platform Developer Intern", "Software Engineering")
        self.check("Email Marketing Intern", "Other")

    def test_falls_back_to_category(self):
        self.check("Summer Intern", "Hardware", category="Hardware")
        self.check("Summer Intern", "Other", category="Other")


class ParseLocationTest(unittest.TestCase):
    def test_city_state(self):
        loc = parse_location("Santa Clara, CA")
        self.assertEqual((loc.city, loc.region, loc.country, loc.remote), ("Santa Clara", "CA", "US", False))

    def test_full_state_name(self):
        loc = parse_location("Maryland")
        self.assertEqual((loc.region, loc.country), ("MD", "US"))

    def test_canada_and_uk(self):
        self.assertEqual(parse_location("Toronto, ON, Canada").country, "Canada")
        self.assertEqual(parse_location("Toronto, ON").region, "ON")
        self.assertEqual(parse_location("London, UK").country, "UK")

    def test_aliases(self):
        loc = parse_location("NYC")
        self.assertEqual((loc.city, loc.region), ("New York", "NY"))
        self.assertEqual(parse_location("SF").region, "CA")

    def test_remote(self):
        loc = parse_location("Remote in USA")
        self.assertTrue(loc.remote)
        self.assertEqual(loc.country, "US")
        self.assertTrue(parse_location("Remote").remote)

    def test_unknown_single_token_is_city(self):
        loc = parse_location("Springfield")
        self.assertEqual((loc.city, loc.country), ("Springfield", None))


class NormalizeTermsTest(unittest.TestCase):
    def test_keeps_valid_dedupes_and_title_cases(self):
        self.assertEqual(normalize_terms(["summer 2027", "Summer 2027", "Fall 2026"]), ["Summer 2027", "Fall 2026"])

    def test_drops_garbage(self):
        self.assertEqual(normalize_terms(["N/A", "", None, "Summer 27"]), [])
        self.assertEqual(normalize_terms(None), [])


class CleanListingTest(unittest.TestCase):
    RAW = {
        "id": "abc", "company_name": " Acme ", "title": "Data  Analyst   Intern",
        "category": "AI/ML/Data", "active": True, "terms": ["Summer 2027", "N/A"],
        "date_posted": 1790000000, "date_updated": 1790000000,
        "url": "https://example.com", "locations": ["Austin, TX", "  "],
        "sponsorship": "Other", "degrees": ["Bachelor's", "Bachelor's"], "is_visible": True,
    }

    def test_happy_path(self):
        row = clean_listing(self.RAW)
        self.assertEqual(row["company"], "Acme")
        self.assertEqual(row["title"], "Data Analyst Intern")
        self.assertEqual(row["role"], "Data Analytics")
        self.assertEqual(row["terms"], ["Summer 2027"])
        self.assertEqual(row["degrees"], ["Bachelor's"])
        self.assertEqual(len(row["locations"]), 1)
        self.assertEqual(row["posted"], "2026-09-21")

    def test_rejects_incomplete_or_hidden(self):
        for missing in ("id", "title", "company_name"):
            with self.subTest(missing=missing):
                self.assertIsNone(clean_listing({**self.RAW, missing: ""}))
        self.assertIsNone(clean_listing({**self.RAW, "is_visible": False}))


if __name__ == "__main__":
    unittest.main()
