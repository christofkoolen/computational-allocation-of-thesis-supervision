from __future__ import annotations

import unittest
import zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from thesis_allocation.similarity import TfidfSimilarity
from thesis_allocation.webapp import (
    run_pipeline_frames,
    template_zip_bytes,
)


class WebAppTests(unittest.TestCase):
    def test_template_download_contains_three_readable_workbooks(self) -> None:
        with zipfile.ZipFile(BytesIO(template_zip_bytes())) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {
                    "researchers.xlsx",
                    "student_preferences.xlsx",
                    "topics.xlsx",
                },
            )
            researchers = pd.read_excel(
                BytesIO(archive.read("researchers.xlsx"))
            )

        self.assertIn("full_name", researchers.columns)
        self.assertIn("daily_supervisor_maximum_theses", researchers.columns)

    def test_browser_pipeline_returns_one_result_bundle(self) -> None:
        researchers = pd.DataFrame(
            [
                {
                    "full_name": "Alice",
                    "email": "alice@example.org",
                    "profile_description": "privacy law safeguards",
                    "daily_supervisor_minimum_theses": 0,
                    "daily_supervisor_maximum_theses": 1,
                    "promotor_minimum_theses": 0,
                    "promotor_maximum_theses": 1,
                },
                {
                    "full_name": "Bob",
                    "email": "bob@example.org",
                    "profile_description": "data engineering systems",
                    "daily_supervisor_minimum_theses": 0,
                    "daily_supervisor_maximum_theses": 1,
                    "promotor_minimum_theses": 0,
                    "promotor_maximum_theses": 1,
                },
            ]
        )
        topics = pd.DataFrame(
            [
                {
                    "topic_id": "privacy",
                    "topic_title": "Privacy law",
                    "topic_description": "privacy rights safeguards",
                    "capacity": 1,
                }
            ]
        )
        preferences = pd.DataFrame(
            [
                {
                    "full_name": "Student",
                    "email": "student@example.org",
                    "preference_1": "privacy",
                }
            ]
        )

        result = run_pipeline_frames(
            researchers,
            topics,
            preferences,
            TfidfSimilarity(),
            retrieve_profile_text=False,
            refresh_profile_text=False,
            request_delay_seconds=0,
            duplicate_policy="keep-last",
            allow_partial=False,
            enforce_distinct_roles=True,
        )

        self.assertEqual(result.assigned_students, 1)
        self.assertEqual(result.preference_cost, 1)
        with zipfile.ZipFile(BytesIO(result.download_bundle())) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {
                    "final_assignments.xlsx",
                    "researchers_enriched.xlsx",
                    "run_report.json",
                    "supervisor_summary.xlsx",
                    "topic_assignments.xlsx",
                },
            )

    def test_streamlit_app_starts_and_navigates(self) -> None:
        root = Path(__file__).resolve().parents[1]
        app = AppTest.from_file(str(root / "streamlit_app.py")).run(timeout=10)

        self.assertFalse(app.exception)
        self.assertEqual(
            app.title[0].value,
            "Thesis allocation and supervision",
        )
        app.sidebar.radio[0].set_value("Input templates").run(timeout=10)
        self.assertFalse(app.exception)
        self.assertEqual(app.header[0].value, "Input templates")


if __name__ == "__main__":
    unittest.main()
