from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from thesis_allocation.cli import main


class ManualReviewCarryOverTests(unittest.TestCase):
    def test_all_9998_students_can_complete_without_previous_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            researchers = root / "researchers.xlsx"
            topics = root / "topics.xlsx"
            preferences = root / "student_preferences.xlsx"
            output = root / "output"

            pd.DataFrame(
                [
                    {
                        "full_name": "Researcher",
                        "email": "researcher@example.org",
                        "supervision_languages": "English",
                        "profile_description": "general research",
                        "daily_supervisor_minimum_theses": 0,
                        "daily_supervisor_maximum_theses": 2,
                        "promotor_minimum_theses": 0,
                        "promotor_maximum_theses": 2,
                    }
                ]
            ).to_excel(researchers, index=False)
            pd.DataFrame(
                [
                    {
                        "topic_id": "current-topic",
                        "topic_title": "Current topic",
                        "topic_description": "current description",
                        "capacity": 2,
                    }
                ]
            ).to_excel(topics, index=False)
            pd.DataFrame(
                [
                    {
                        "full_name": "Carry One",
                        "email": "carry1@example.org",
                        "preference_1": 9998,
                        "preference_1_languages": "",
                        "preference_2": "",
                        "preference_2_languages": "",
                        "preference_3": "",
                        "preference_3_languages": "",
                    },
                    {
                        "full_name": "Carry Two",
                        "email": "carry2@example.org",
                        "preference_1": 9998,
                        "preference_1_languages": "",
                        "preference_2": "",
                        "preference_2_languages": "",
                        "preference_3": "",
                        "preference_3_languages": "",
                    },
                ]
            ).to_excel(preferences, index=False)

            exit_code = main(
                [
                    "run",
                    "--researchers",
                    str(researchers),
                    "--topics",
                    str(topics),
                    "--preferences",
                    str(preferences),
                    "--output-directory",
                    str(output),
                    "--skip-scrape",
                    "--backend",
                    "tfidf",
                ]
            )

            self.assertEqual(exit_code, 0)
            final = pd.read_excel(output / "final_assignments.xlsx")
            self.assertEqual(len(final), 2)
            self.assertTrue(final["assigned_topic_id"].astype(str).eq("9998").all())
            self.assertTrue(
                final["topic_assignment_source"]
                .eq("carry_over_manual_review")
                .all()
            )
            self.assertTrue(
                final["daily_supervisor_assignment_source"].eq("manual_review").all()
            )
            self.assertTrue(
                final["promotor_assignment_source"].eq("manual_review").all()
            )

            report = json.loads((output / "run_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["carry_over_students"], 2)
            self.assertEqual(report["manual_review_students"], 2)
            self.assertEqual(report["preference_cost"], 0)


if __name__ == "__main__":
    unittest.main()
