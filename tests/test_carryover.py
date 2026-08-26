from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from thesis_allocation.cli import main


class CarryOverTests(unittest.TestCase):
    def test_complete_run_carries_topic_and_supervision_and_reserves_capacity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            researchers, topics, preferences, previous = self._write_inputs(root)
            output = root / "output"

            exit_code = main(
                [
                    "run",
                    "--researchers",
                    str(researchers),
                    "--topics",
                    str(topics),
                    "--preferences",
                    str(preferences),
                    "--previous-final-assignments",
                    str(previous),
                    "--output-directory",
                    str(output),
                    "--skip-scrape",
                    "--backend",
                    "tfidf",
                ]
            )

            self.assertEqual(exit_code, 0)
            final = pd.read_excel(output / "final_assignments.xlsx").set_index("email")
            carried = final.loc["carry@example.org"]
            self.assertEqual(carried["assigned_topic_id"], "old-topic")
            self.assertEqual(carried["assigned_topic"], "Previous-year thesis")
            self.assertEqual(
                carried["assigned_topic_description"],
                "legacy competition regulation thesis",
            )
            self.assertEqual(carried["assigned_language"], "English")
            self.assertEqual(carried["daily_supervisor_email"], "daily-old@example.org")
            self.assertEqual(carried["promotor_email"], "promotor-old@example.org")
            self.assertEqual(carried["daily_supervisor_assignment_source"], "carry_over")
            self.assertEqual(carried["promotor_assignment_source"], "carry_over")

            new = final.loc["new@example.org"]
            self.assertEqual(new["assigned_topic_id"], "privacy")
            self.assertEqual(
                new["assigned_topic_description"],
                "privacy rights safeguards",
            )
            self.assertEqual(new["daily_supervisor_email"], "daily-new@example.org")
            self.assertEqual(new["promotor_email"], "promotor-new@example.org")

            report = json.loads((output / "run_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["assigned_students"], 2)
            self.assertEqual(report["carry_over_students"], 1)
            self.assertEqual(report["manual_review_students"], 0)
            self.assertEqual(report["preference_cost"], 1)

    def test_missing_previous_supervisor_is_cleared_and_reassigned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            researchers, topics, preferences, previous = self._write_inputs(root)
            previous_table = pd.read_excel(previous)
            previous_table.loc[0, "daily_supervisor"] = "Departed Researcher"
            previous_table.loc[0, "daily_supervisor_email"] = "departed@example.org"
            previous_table.to_excel(previous, index=False)
            output = root / "output"

            exit_code = main(
                [
                    "run",
                    "--researchers",
                    str(researchers),
                    "--topics",
                    str(topics),
                    "--preferences",
                    str(preferences),
                    "--previous-final-assignments",
                    str(previous),
                    "--output-directory",
                    str(output),
                    "--skip-scrape",
                    "--backend",
                    "tfidf",
                ]
            )

            self.assertEqual(exit_code, 0)
            final = pd.read_excel(output / "final_assignments.xlsx").set_index("email")
            carried = final.loc["carry@example.org"]
            self.assertEqual(carried["assigned_topic_id"], "old-topic")
            self.assertEqual(carried["assigned_topic"], "Previous-year thesis")
            self.assertEqual(carried["promotor_email"], "promotor-old@example.org")
            self.assertEqual(carried["daily_supervisor_email"], "daily-old@example.org")
            self.assertNotEqual(
                carried["daily_supervisor_assignment_source"],
                "carry_over",
            )
            report = json.loads((output / "run_report.json").read_text(encoding="utf-8"))
            self.assertTrue(
                any("departed@example.org" in warning for warning in report["warnings"])
            )

    def test_carry_over_ignores_current_topic_with_same_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            researchers, topics, preferences, previous = self._write_inputs(root)

            previous_table = pd.read_excel(previous)
            previous_table.loc[0, "daily_supervisor"] = "Departed Researcher"
            previous_table.loc[0, "daily_supervisor_email"] = "departed@example.org"
            previous_table.to_excel(previous, index=False)

            topics_table = pd.read_excel(topics)
            topics_table = pd.concat(
                [
                    topics_table,
                    pd.DataFrame(
                        [
                            {
                                "topic_id": "old-topic",
                                "topic_title": "Reused current-year topic",
                                "topic_description": "privacy rights safeguards",
                                "submitter_email": "daily-new@example.org",
                                "capacity": 1,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
            topics_table.to_excel(topics, index=False)
            output = root / "output"

            exit_code = main(
                [
                    "run",
                    "--researchers",
                    str(researchers),
                    "--topics",
                    str(topics),
                    "--preferences",
                    str(preferences),
                    "--previous-final-assignments",
                    str(previous),
                    "--output-directory",
                    str(output),
                    "--skip-scrape",
                    "--backend",
                    "tfidf",
                ]
            )

            self.assertEqual(exit_code, 0)
            final = pd.read_excel(output / "final_assignments.xlsx").set_index("email")
            carried = final.loc["carry@example.org"]
            self.assertEqual(carried["assigned_topic"], "Previous-year thesis")
            self.assertEqual(
                carried["assigned_topic_description"],
                "legacy competition regulation thesis",
            )
            self.assertEqual(carried["daily_supervisor_email"], "daily-old@example.org")
            self.assertNotEqual(
                carried["daily_supervisor_email"],
                "daily-new@example.org",
            )

    def test_excess_carry_over_capacity_is_reassigned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            researchers, topics, preferences, previous = self._write_inputs(root)

            researcher_table = pd.read_excel(researchers)
            researcher_table.loc[
                researcher_table["email"].eq("daily-old@example.org"),
                "daily_supervisor_maximum_theses",
            ] = 2
            researcher_table.loc[
                researcher_table["email"].eq("promotor-old@example.org"),
                "promotor_maximum_theses",
            ] = 3
            researcher_table.to_excel(researchers, index=False)

            carry_students = []
            previous_rows = []
            for number in (1, 2, 3):
                email = f"carry{number}@example.org"
                carry_students.append(
                    {
                        "full_name": f"Carry Student {number}",
                        "email": email,
                        "preference_1": 9998,
                        "preference_1_languages": "",
                        "preference_2": "",
                        "preference_2_languages": "",
                        "preference_3": "",
                        "preference_3_languages": "",
                    }
                )
                previous_rows.append(
                    {
                        "full_name": f"Carry Student {number}",
                        "email": email,
                        "assigned_topic_id": f"old-topic-{number}",
                        "assigned_topic": f"Previous thesis {number}",
                        "assigned_topic_description": "legacy competition regulation thesis",
                        "assigned_language": "English",
                        "daily_supervisor": "Daily Old",
                        "daily_supervisor_email": "daily-old@example.org",
                        "promotor": "Promotor Old",
                        "promotor_email": "promotor-old@example.org",
                    }
                )

            pd.DataFrame(carry_students).to_excel(preferences, index=False)
            pd.DataFrame(previous_rows).to_excel(previous, index=False)
            output = root / "output"

            exit_code = main(
                [
                    "run",
                    "--researchers",
                    str(researchers),
                    "--topics",
                    str(topics),
                    "--preferences",
                    str(preferences),
                    "--previous-final-assignments",
                    str(previous),
                    "--output-directory",
                    str(output),
                    "--skip-scrape",
                    "--backend",
                    "tfidf",
                ]
            )

            self.assertEqual(exit_code, 0)
            final = pd.read_excel(output / "final_assignments.xlsx").set_index("email")
            self.assertEqual(
                final.loc["carry1@example.org", "daily_supervisor_email"],
                "daily-old@example.org",
            )
            self.assertEqual(
                final.loc["carry2@example.org", "daily_supervisor_email"],
                "daily-old@example.org",
            )
            self.assertEqual(
                final.loc["carry3@example.org", "daily_supervisor_email"],
                "daily-new@example.org",
            )
            report = json.loads((output / "run_report.json").read_text(encoding="utf-8"))
            self.assertTrue(
                any("current maximum capacity" in warning for warning in report["warnings"])
            )

    def test_previous_record_is_ignored_when_repeat_student_chooses_new_topics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            researchers, topics, preferences, previous = self._write_inputs(root)
            preference_table = pd.read_excel(preferences)
            preference_table = preference_table[
                preference_table["email"].eq("carry@example.org")
            ].copy()
            preference_table.loc[:, "preference_1"] = "privacy"
            preference_table.loc[:, "preference_2"] = "data"
            preference_table.loc[:, "preference_3"] = "contracts"
            preference_table.loc[:, "preference_1_languages"] = "English"
            preference_table.loc[:, "preference_2_languages"] = "English"
            preference_table.loc[:, "preference_3_languages"] = "English"
            preference_table.to_excel(preferences, index=False)
            output = root / "output"

            exit_code = main(
                [
                    "run",
                    "--researchers",
                    str(researchers),
                    "--topics",
                    str(topics),
                    "--preferences",
                    str(preferences),
                    "--previous-final-assignments",
                    str(previous),
                    "--output-directory",
                    str(output),
                    "--skip-scrape",
                    "--backend",
                    "tfidf",
                ]
            )

            self.assertEqual(exit_code, 0)
            final = pd.read_excel(output / "final_assignments.xlsx").iloc[0]
            self.assertEqual(final["assigned_topic_id"], "privacy")
            self.assertEqual(final["topic_assignment_source"], "ranked_preference")
            report = json.loads((output / "run_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["carry_over_students"], 0)
            self.assertEqual(report["manual_review_students"], 0)

    def test_9998_without_previous_final_assignments_is_marked_for_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            researchers, topics, preferences, previous = self._write_inputs(root)
            del previous
            output = root / "output"

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
            marker = "CARRY-OVER STUDENT - MANUAL REVIEW NEEDED"
            final = pd.read_excel(output / "final_assignments.xlsx").set_index("email")
            carried = final.loc["carry@example.org"]
            self.assertEqual(str(carried["assigned_topic_id"]), "9998")
            self.assertEqual(carried["assigned_topic"], marker)
            self.assertEqual(carried["assigned_topic_description"], marker)
            self.assertEqual(carried["assigned_language"], marker)
            self.assertEqual(carried["daily_supervisor"], marker)
            self.assertEqual(carried["promotor"], marker)
            self.assertTrue(pd.isna(carried["daily_supervisor_email"]))
            self.assertTrue(pd.isna(carried["promotor_email"]))
            self.assertEqual(
                carried["topic_assignment_source"],
                "carry_over_manual_review",
            )
            self.assertEqual(
                carried["daily_supervisor_assignment_source"],
                "manual_review",
            )
            self.assertEqual(
                carried["promotor_assignment_source"],
                "manual_review",
            )

            new = final.loc["new@example.org"]
            self.assertEqual(new["assigned_topic_id"], "privacy")
            self.assertEqual(new["daily_supervisor_email"], "daily-new@example.org")
            self.assertEqual(new["promotor_email"], "promotor-new@example.org")

            topics_output = pd.read_excel(output / "topic_assignments.xlsx").set_index(
                "email"
            )
            self.assertEqual(
                topics_output.loc["carry@example.org", "assigned_topic"],
                marker,
            )

            report = json.loads((output / "run_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["assigned_students"], 1)
            self.assertEqual(report["carry_over_students"], 1)
            self.assertEqual(report["manual_review_students"], 1)
            self.assertTrue(
                any("manual review" in warning.casefold() for warning in report["warnings"])
            )

    @staticmethod
    def _write_inputs(root: Path) -> tuple[Path, Path, Path, Path]:
        researchers = root / "researchers.xlsx"
        topics = root / "topics.xlsx"
        preferences = root / "student_preferences.xlsx"
        previous = root / "previous_final_assignments.xlsx"

        pd.DataFrame(
            [
                {
                    "full_name": "Daily Old",
                    "email": "daily-old@example.org",
                    "supervision_languages": "English",
                    "profile_description": "legacy competition regulation thesis",
                    "daily_supervisor_minimum_theses": 0,
                    "daily_supervisor_maximum_theses": 1,
                    "promotor_minimum_theses": 0,
                    "promotor_maximum_theses": 0,
                },
                {
                    "full_name": "Promotor Old",
                    "email": "promotor-old@example.org",
                    "supervision_languages": "English",
                    "profile_description": "legacy competition regulation",
                    "daily_supervisor_minimum_theses": 0,
                    "daily_supervisor_maximum_theses": 0,
                    "promotor_minimum_theses": 0,
                    "promotor_maximum_theses": 1,
                },
                {
                    "full_name": "Daily New",
                    "email": "daily-new@example.org",
                    "supervision_languages": "English",
                    "profile_description": "privacy rights safeguards",
                    "daily_supervisor_minimum_theses": 0,
                    "daily_supervisor_maximum_theses": 1,
                    "promotor_minimum_theses": 0,
                    "promotor_maximum_theses": 0,
                },
                {
                    "full_name": "Promotor New",
                    "email": "promotor-new@example.org",
                    "supervision_languages": "English",
                    "profile_description": "privacy rights safeguards",
                    "daily_supervisor_minimum_theses": 0,
                    "daily_supervisor_maximum_theses": 0,
                    "promotor_minimum_theses": 0,
                    "promotor_maximum_theses": 1,
                },
            ]
        ).to_excel(researchers, index=False)

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
                    "topic_title": "Data systems",
                    "topic_description": "data systems",
                    "capacity": 1,
                },
                {
                    "topic_id": "contracts",
                    "topic_title": "Contract law",
                    "topic_description": "commercial contracts",
                    "capacity": 1,
                },
            ]
        ).to_excel(topics, index=False)

        pd.DataFrame(
            [
                {
                    "full_name": "Carry Student",
                    "email": "carry@example.org",
                    "preference_1": 9998,
                    "preference_1_languages": "",
                    "preference_2": "",
                    "preference_2_languages": "",
                    "preference_3": "",
                    "preference_3_languages": "",
                },
                {
                    "full_name": "New Student",
                    "email": "new@example.org",
                    "preference_1": "privacy",
                    "preference_1_languages": "English",
                    "preference_2": "data",
                    "preference_2_languages": "English",
                    "preference_3": "contracts",
                    "preference_3_languages": "English",
                },
            ]
        ).to_excel(preferences, index=False)

        pd.DataFrame(
            [
                {
                    "full_name": "Carry Student",
                    "email": "carry@example.org",
                    "assigned_topic_id": "old-topic",
                    "assigned_topic": "Previous-year thesis",
                    "assigned_topic_description": "legacy competition regulation thesis",
                    "assigned_language": "English",
                    "daily_supervisor": "Daily Old",
                    "daily_supervisor_email": "daily-old@example.org",
                    "promotor": "Promotor Old",
                    "promotor_email": "promotor-old@example.org",
                }
            ]
        ).to_excel(previous, index=False)
        return researchers, topics, preferences, previous


if __name__ == "__main__":
    unittest.main()
