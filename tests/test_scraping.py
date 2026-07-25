from __future__ import annotations

import unittest

import pandas as pd

from thesis_allocation.scraping import (
    derive_publications_url,
    enrich_researchers,
    extract_visible_text,
)


class ScrapingTests(unittest.TestCase):
    def test_extracts_body_text_and_ignores_non_visible_content(self) -> None:
        html = """
        <html>
          <head><title>Ignored title</title><style>.hidden {}</style></head>
          <body>
            <h1>Research profile</h1>
            <script>secret()</script>
            <p>Privacy and technology law.</p>
          </body>
        </html>
        """

        text = extract_visible_text(html)

        self.assertEqual(text, "Research profile Privacy and technology law.")
        self.assertNotIn("secret", text)
        self.assertNotIn("Ignored", text)

    def test_derives_lirias_url_from_staff_profile(self) -> None:
        self.assertEqual(
            derive_publications_url("https://example.org/staff/012345"),
            "https://lirias.kuleuven.be/cv?Username=u12345",
        )

    def test_enrichment_preserves_rows_and_records_status(self) -> None:
        researchers = pd.DataFrame(
            [
                {
                    "full_name": "Alice",
                    "email": "Alice@Example.org",
                    "profile_url": "https://example.org/staff/0123",
                }
            ]
        )
        pages = {
            "https://example.org/staff/0123": (
                "<html><body>Privacy researcher</body></html>"
            ),
            "https://lirias.kuleuven.be/cv?Username=u123": (
                "<html><body>Publication one</body></html>"
            ),
        }

        def fetcher(url: str, *, timeout: float) -> str:
            self.assertEqual(timeout, 5.0)
            return pages[url]

        result = enrich_researchers(
            researchers,
            timeout=5.0,
            delay_seconds=0,
            fetcher=fetcher,
        )
        row = result.researchers.iloc[0]

        self.assertEqual(row["email"], "alice@example.org")
        self.assertEqual(row["profile_description"], "Privacy researcher")
        self.assertEqual(row["publication_list"], "Publication one")
        self.assertEqual(row["profile_scrape_status"], "ok")
        self.assertEqual(row["publications_scrape_status"], "ok")
        self.assertEqual(result.warnings, ())


if __name__ == "__main__":
    unittest.main()

