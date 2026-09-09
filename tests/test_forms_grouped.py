from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path

import pandas as pd

from thesis_allocation.forms import normalize_forms_submissions
from thesis_allocation.grouped import allocate_forms_submissions
from thesis_allocation.cli import main
from thesis_allocation.similarity import TfidfSimilarity


def researcher(
    name: str,
    email: str,
    languages: str,
    *,
    daily_max: int,
    promotor_max: int,
) -> dict[str, object]:
    return {
        "full_name": name,
        "email": email,
        "supervision_languages": languages,
        "profile_description": "law technology privacy",
        "daily_supervisor_minimum_theses": 0,
        "daily_supervisor_maximum_theses": daily_max,
        "promotor_minimum_theses": 0,
        "promotor_maximum_theses": promotor_max,
    }


def ranked_submission(
    name: str,
    email: str,
    choices: tuple[str, str, str],
    languages: tuple[str, str, str],
    *,
    partner: tuple[str, str, str] | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "full_name": name,
        "email": email,
        "student_number": "r123",
        "thesis_type": (
            "Dual thesis: I will write my thesis together with one other student"
            if partner
            else "Individual thesis: I will write my thesis individually"
        ),
        "thesis_allocation_status": (
            "New topic: I am requesting a new thesis allocation and will choose "
            "from the provided list"
        ),
        "topic_preference_1": choices[0],
        "topic_preference_1_languages": languages[0],
        "topic_preference_2": choices[1],
        "topic_preference_2_languages": languages[1],
        "topic_preference_3": choices[2],
        "topic_preference_3_languages": languages[2],
    }
    if partner:
        row.update(
            {
                "partner_full_name": partner[0],
                "partner_email": partner[1],
                "partner_student_number": partner[2],
                "dual_thesis_confirmation": "Confirmed",
            }
        )
    return row


class FormsNormalizationTests(unittest.TestCase):
    def test_routes_dedicated_sections_without_reserved_topic_ids(self) -> None:
        rows = [
            ranked_submission(
                "Regular", "regular@example.org", ("1", "2", "3"),
                ("Dutch", "English; Dutch", "English"),
            ),
            {
                "full_name": "Own",
                "email": "own@example.org",
                "student_number": "r124",
                "thesis_type": "Individual thesis: I will write my thesis individually",
                "thesis_allocation_status": "Self-proposed topic: I propose my own",
                "self_proposed_thesis_title": "Own title",
                "self_proposed_thesis_description": "Own description",
                "self_proposed_thesis_language": "English",
            },
            {
                "full_name": "Carry",
                "email": "carry@example.org",
                "student_number": "r125",
                "thesis_type": "Individual thesis: I will write my thesis individually",
                "thesis_allocation_status": "Carry-over topic: continuing last year",
                "carry_over_thesis_topic": "Existing thesis",
                "carry_over_thesis_language": "Dutch",
                "daily_supervisor_email": "daily@example.org",
                "thesis_promotor_email": "promotor@example.org",
            },
        ]

        normalized = normalize_forms_submissions(pd.DataFrame(rows))

        self.assertEqual(
            normalized["allocation_path"].tolist(),
            ["ranked", "self_proposed", "carry_over"],
        )
        self.assertNotIn("9998", normalized.to_string())
        self.assertNotIn("9999", normalized.to_string())


class GroupedAllocationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = TfidfSimilarity()
        self.topics = pd.DataFrame(
            [
                {"topic_id": "A", "topic_title": "Alpha", "capacity": 1},
                {"topic_id": "B", "topic_title": "Beta", "capacity": 2},
                {"topic_id": "C", "topic_title": "Gamma", "capacity": 2},
            ]
        )

    def test_dual_thesis_uses_one_topic_and_one_slot_per_role(self) -> None:
        submissions = pd.DataFrame(
            [
                ranked_submission(
                    "Primary",
                    "primary@example.org",
                    ("A", "B", "C"),
                    ("English", "English", "English"),
                    partner=("Partner", "partner@example.org", "r999"),
                )
            ]
        )
        researchers = pd.DataFrame(
            [
                researcher("Daily", "daily@example.org", "English", daily_max=1, promotor_max=0),
                researcher("Promotor", "promotor@example.org", "English", daily_max=0, promotor_max=1),
            ]
        )

        result = allocate_forms_submissions(
            submissions, self.topics, researchers, self.backend
        )

        self.assertEqual(result.assigned_students, 2)
        self.assertEqual(result.assigned_theses, 1)
        self.assertEqual(result.dual_theses, 1)
        self.assertEqual(len(result.assignments), 2)
        self.assertEqual(result.assignments["thesis_group_id"].nunique(), 1)
        self.assertEqual(result.assignments["assigned_topic_id"].unique().tolist(), ["A"])
        daily_load = result.summary.set_index("email").at[
            "daily@example.org", "assigned_daily_supervisor_theses"
        ]
        self.assertEqual(daily_load, 1)

    def test_dual_preference_cost_is_weighted_for_both_students(self) -> None:
        submissions = pd.DataFrame(
            [
                ranked_submission(
                    "Pair primary",
                    "pair@example.org",
                    ("A", "C", "B"),
                    ("English", "English", "English"),
                    partner=("Pair partner", "partner@example.org", "r222"),
                ),
                ranked_submission(
                    "Individual",
                    "individual@example.org",
                    ("A", "B", "C"),
                    ("English", "English", "English"),
                ),
            ]
        )
        researchers = pd.DataFrame(
            [
                researcher("Daily", "daily@example.org", "English", daily_max=2, promotor_max=0),
                researcher("Promotor", "promotor@example.org", "English", daily_max=0, promotor_max=2),
            ]
        )

        result = allocate_forms_submissions(
            submissions, self.topics, researchers, self.backend
        )
        groups = result.group_assignments.set_index("email")

        self.assertEqual(groups.at["pair@example.org", "assigned_topic_id"], "A")
        self.assertEqual(groups.at["individual@example.org", "assigned_topic_id"], "B")
        self.assertEqual(result.preference_cost, 4)

    def test_language_order_falls_back_when_first_language_has_no_capacity(self) -> None:
        submissions = pd.DataFrame(
            [
                {
                    "full_name": "Carry",
                    "email": "carry@example.org",
                    "student_number": "r100",
                    "thesis_type": "Individual thesis: I will write my thesis individually",
                    "thesis_allocation_status": "Carry-over topic: continuing last year",
                    "carry_over_thesis_topic": "Existing thesis",
                    "carry_over_thesis_language": "Dutch",
                    "daily_supervisor_email": "daily.nl@example.org",
                    "thesis_promotor_email": "promotor.nl@example.org",
                },
                ranked_submission(
                    "New",
                    "new@example.org",
                    ("A", "B", "C"),
                    ("Dutch; English", "English", "English"),
                ),
            ]
        )
        researchers = pd.DataFrame(
            [
                researcher("Daily NL", "daily.nl@example.org", "Dutch", daily_max=1, promotor_max=0),
                researcher("Promotor NL", "promotor.nl@example.org", "Dutch", daily_max=0, promotor_max=1),
                researcher("Daily EN", "daily.en@example.org", "English", daily_max=1, promotor_max=0),
                researcher("Promotor EN", "promotor.en@example.org", "English", daily_max=0, promotor_max=1),
            ]
        )

        result = allocate_forms_submissions(
            submissions, self.topics, researchers, self.backend
        )
        groups = result.group_assignments.set_index("email")

        self.assertEqual(groups.at["new@example.org", "assigned_topic_id"], "A")
        self.assertEqual(groups.at["new@example.org", "assigned_language"], "English")
        self.assertEqual(groups.at["new@example.org", "assigned_language_rank"], 2)

    def test_topic_submitter_keeps_absolute_role_priority(self) -> None:
        submissions = pd.DataFrame(
            [
                ranked_submission(
                    "Student",
                    "student@example.org",
                    ("A", "B", "C"),
                    ("English", "English", "English"),
                )
            ]
        )
        topics = self.topics.copy()
        topics.loc[topics["topic_id"].eq("A"), "submitter_email"] = (
            "submitter@example.org"
        )
        researchers = pd.DataFrame(
            [
                researcher("Submitter", "submitter@example.org", "English", daily_max=1, promotor_max=0),
                researcher("Better match", "better@example.org", "English", daily_max=1, promotor_max=0),
                researcher("Promotor", "promotor@example.org", "English", daily_max=0, promotor_max=1),
            ]
        )
        researchers.loc[
            researchers["email"].eq("submitter@example.org"),
            "profile_description",
        ] = "medieval history"

        result = allocate_forms_submissions(
            submissions, topics, researchers, self.backend
        )
        assignment = result.group_assignments.iloc[0]

        self.assertEqual(
            assignment["daily_supervisor_email"], "submitter@example.org"
        )
        self.assertEqual(
            assignment["daily_supervisor_assignment_source"], "topic_submitter"
        )

    def test_complete_cli_auto_detects_forms_export(self) -> None:
        submissions = pd.DataFrame(
            [
                ranked_submission(
                    "Student",
                    "student@example.org",
                    ("A", "B", "C"),
                    ("English", "English", "English"),
                )
            ]
        )
        researchers = pd.DataFrame(
            [
                researcher("Daily", "daily@example.org", "English", daily_max=1, promotor_max=0),
                researcher("Promotor", "promotor@example.org", "English", daily_max=0, promotor_max=1),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            submissions.to_excel(root / "forms.xlsx", index=False)
            self.topics.to_excel(root / "topics.xlsx", index=False)
            researchers.to_excel(root / "researchers.xlsx", index=False)

            exit_code = main(
                [
                    "run",
                    "--preferences",
                    str(root / "forms.xlsx"),
                    "--topics",
                    str(root / "topics.xlsx"),
                    "--researchers",
                    str(root / "researchers.xlsx"),
                    "--output-directory",
                    str(root / "output"),
                    "--skip-scrape",
                    "--backend",
                    "tfidf",
                ]
            )

            self.assertEqual(exit_code, 0)
            final = pd.read_excel(root / "output" / "final_assignments.xlsx")
            report = json.loads(
                (root / "output" / "run_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(final.iloc[0]["assigned_topic_id"], "A")
            self.assertEqual(report["input_format"], "microsoft_forms")
            self.assertEqual(report["assigned_students"], 1)
            self.assertEqual(report["assigned_theses"], 1)


if __name__ == "__main__":
    unittest.main()
