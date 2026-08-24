from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from thesis_allocation.cli import main


class CliTests(unittest.TestCase):
    def test_creates_templates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            exit_code = main(["create-templates", directory])

            self.assertEqual(exit_code, 0)
            self.assertTrue((Path(directory) / "researchers.xlsx").is_file())
            self.assertTrue((Path(directory) / "topics.xlsx").is_file())

            researchers = pd.read_excel(Path(directory) / "researchers.xlsx")
            topics = pd.read_excel(Path(directory) / "topics.xlsx")
            preferences = pd.read_excel(Path(directory) / "student_preferences.xlsx")

            self.assertIn("supervision_languages", researchers.columns)
            self.assertNotIn("supervision_languages", topics.columns)
            self.assertIn("own_topic_description", preferences.columns)

    def test_allocates_csv_inputs_without_machine_specific_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            topics_path = root / "topics.csv"
            preferences_path = root / "preferences.csv"
            output_path = root / "assignments.csv"
            pd.DataFrame(
                [
                    {"topic_id": "one", "topic_title": "Topic One", "capacity": 1},
                    {"topic_id": "two", "topic_title": "Topic Two", "capacity": 1},
                    {"topic_id": "three", "topic_title": "Topic Three", "capacity": 1},
                ]
            ).to_csv(topics_path, index=False)
            pd.DataFrame(
                [
                    {
                        "full_name": "Student",
                        "email": "student@example.org",
                        "preference_1": "one",
                        "preference_1_languages": "English",
                        "preference_2": "two",
                        "preference_2_languages": "Dutch",
                        "preference_3": "three",
                        "preference_3_languages": "French",
                    }
                ]
            ).to_csv(preferences_path, index=False)

            exit_code = main(
                [
                    "allocate-topics",
                    "--preferences",
                    str(preferences_path),
                    "--topics",
                    str(topics_path),
                    "--output",
                    str(output_path),
                ]
            )

            self.assertEqual(exit_code, 0)
            output = pd.read_csv(output_path)
            self.assertEqual(output.iloc[0]["assigned_topic_id"], "one")
            self.assertEqual(output.iloc[0]["assigned_language"], "English")

    def test_runs_the_complete_offline_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_directory = root / "input"
            output_directory = root / "output"
            input_directory.mkdir()

            researchers_path = input_directory / "researchers.xlsx"
            topics_path = input_directory / "topics.xlsx"
            preferences_path = input_directory / "preferences.xlsx"
            pd.DataFrame(
                [
                    {
                        "full_name": "Alice",
                        "email": "alice@example.org",
                        "supervision_languages": "English",
                        "profile_description": "privacy law safeguards",
                        "daily_supervisor_minimum_theses": 0,
                        "daily_supervisor_maximum_theses": 1,
                        "promotor_minimum_theses": 0,
                        "promotor_maximum_theses": 1,
                    },
                    {
                        "full_name": "Bob",
                        "email": "bob@example.org",
                        "supervision_languages": "English",
                        "profile_description": "data engineering systems",
                        "daily_supervisor_minimum_theses": 0,
                        "daily_supervisor_maximum_theses": 1,
                        "promotor_minimum_theses": 0,
                        "promotor_maximum_theses": 1,
                    },
                ]
            ).to_excel(researchers_path, index=False)
            pd.DataFrame(
                [
                    {
                        "topic_id": "privacy",
                        "topic_title": "Privacy law",
                        "topic_description": "privacy rights safeguards",
                        "capacity": 1,
                    },
                    {
                        "topic_id": "data",
                        "topic_title": "Data engineering",
                        "topic_description": "data engineering systems",
                        "capacity": 1,
                    },
                    {
                        "topic_id": "contracts",
                        "topic_title": "Contract law",
                        "topic_description": "commercial contracts",
                        "capacity": 1,
                    },
                ]
            ).to_excel(topics_path, index=False)
            pd.DataFrame(
                [
                    {
                        "full_name": "Student",
                        "email": "student@example.org",
                        "preference_1": "privacy",
                        "preference_1_languages": "English",
                        "preference_2": "data",
                        "preference_2_languages": "English",
                        "preference_3": "contracts",
                        "preference_3_languages": "English",
                    }
                ]
            ).to_excel(preferences_path, index=False)

            exit_code = main(
                [
                    "run",
                    "--researchers",
                    str(researchers_path),
                    "--topics",
                    str(topics_path),
                    "--preferences",
                    str(preferences_path),
                    "--output-directory",
                    str(output_directory),
                    "--skip-scrape",
                    "--backend",
                    "tfidf",
                ]
            )

            self.assertEqual(exit_code, 0)
            expected = {
                "researchers_enriched.xlsx",
                "topic_assignments.xlsx",
                "final_assignments.xlsx",
                "supervisor_summary.xlsx",
                "run_report.json",
            }
            self.assertEqual(
                {path.name for path in output_directory.iterdir()},
                expected,
            )
            final = pd.read_excel(output_directory / "final_assignments.xlsx")
            self.assertEqual(final.iloc[0]["daily_supervisor_email"], "alice@example.org")
            self.assertEqual(final.iloc[0]["promotor_email"], "bob@example.org")
            self.assertEqual(final.iloc[0]["assigned_language"], "English")


if __name__ == "__main__":
    unittest.main()
