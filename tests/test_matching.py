from __future__ import annotations

import unittest

import pandas as pd

from thesis_allocation.errors import InputValidationError
from thesis_allocation.matching import match_supervisors
from thesis_allocation.replacement import reassign_supervision
from thesis_allocation.similarity import TfidfSimilarity


def researcher(
    name: str,
    email: str,
    profile: str,
    *,
    languages: str = "",
    daily_min: int = 0,
    daily_max: int = 1,
    promotor_min: int = 0,
    promotor_max: int = 1,
) -> dict[str, object]:
    return {
        "full_name": name,
        "email": email,
        "appointment": "researcher",
        "supervision_languages": languages,
        "profile_description": profile,
        "publication_list": "",
        "daily_supervisor_minimum_theses": daily_min,
        "daily_supervisor_maximum_theses": daily_max,
        "promotor_minimum_theses": promotor_min,
        "promotor_maximum_theses": promotor_max,
    }


class SupervisorMatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = TfidfSimilarity()
        self.topics = pd.DataFrame(
            [
                {
                    "topic_id": "privacy",
                    "topic_title": "Privacy law",
                    "topic_description": "privacy rights and legal safeguards",
                    "capacity": 1,
                },
                {
                    "topic_id": "data",
                    "topic_title": "Data engineering",
                    "topic_description": "data systems and databases",
                    "capacity": 1,
                },
            ]
        )

    def test_matches_both_roles_globally_and_keeps_them_distinct(self) -> None:
        researchers = pd.DataFrame(
            [
                researcher(
                    "Alice Privacy",
                    "alice@example.org",
                    "privacy law rights safeguards",
                ),
                researcher(
                    "Bob Data",
                    "bob@example.org",
                    "data engineering databases systems",
                ),
            ]
        )
        assignments = pd.DataFrame(
            [
                {
                    "full_name": "Student Privacy",
                    "email": "privacy.student@example.org",
                    "assigned_topic_id": "privacy",
                    "assigned_topic": "Privacy law",
                },
                {
                    "full_name": "Student Data",
                    "email": "data.student@example.org",
                    "assigned_topic_id": "data",
                    "assigned_topic": "Data engineering",
                },
            ]
        )

        result = match_supervisors(
            assignments,
            researchers,
            self.topics,
            self.backend,
        )

        output = result.assignments.set_index("email")
        self.assertEqual(
            output.at["privacy.student@example.org", "daily_supervisor_email"],
            "alice@example.org",
        )
        self.assertEqual(
            output.at["data.student@example.org", "daily_supervisor_email"],
            "bob@example.org",
        )
        self.assertTrue(
            (
                output["daily_supervisor_email"]
                != output["promotor_email"]
            ).all()
        )
        self.assertEqual(
            set(output["promotor_email"]),
            {"alice@example.org", "bob@example.org"},
        )

    def test_researcher_language_filters_daily_supervisor_candidates(self) -> None:
        researchers = pd.DataFrame(
            [
                researcher(
                    "Alice Strong Match",
                    "alice@example.org",
                    "privacy law rights safeguards",
                    languages="Dutch",
                    promotor_max=0,
                ),
                researcher(
                    "Bob English",
                    "bob@example.org",
                    "medieval history",
                    languages="English",
                    promotor_max=0,
                ),
            ]
        )
        assignments = pd.DataFrame(
            [
                {
                    "full_name": "Student",
                    "email": "student@example.org",
                    "assigned_topic_id": "privacy",
                    "assigned_topic": "Privacy law",
                    "assigned_language": "English",
                }
            ]
        )

        result = match_supervisors(
            assignments,
            researchers,
            self.topics,
            self.backend,
            roles=("daily_supervisor",),
        )

        self.assertEqual(
            result.assignments.iloc[0]["daily_supervisor_email"],
            "bob@example.org",
        )

    def test_submitter_priority_requires_language_compatibility(self) -> None:
        researchers = pd.DataFrame(
            [
                researcher(
                    "Alice Submitter",
                    "alice@example.org",
                    "privacy law rights safeguards",
                    languages="Dutch",
                    promotor_max=0,
                ),
                researcher(
                    "Bob English",
                    "bob@example.org",
                    "privacy governance",
                    languages="English",
                    promotor_max=0,
                ),
            ]
        )
        topics = self.topics.copy()
        topics.loc[
            topics["topic_id"] == "privacy",
            "submitter_email",
        ] = "alice@example.org"
        assignments = pd.DataFrame(
            [
                {
                    "full_name": "Student",
                    "email": "student@example.org",
                    "assigned_topic_id": "privacy",
                    "assigned_topic": "Privacy law",
                    "assigned_language": "English",
                }
            ]
        )

        result = match_supervisors(
            assignments,
            researchers,
            topics,
            self.backend,
            roles=("daily_supervisor",),
        )

        output = result.assignments.iloc[0]
        self.assertEqual(output["daily_supervisor_email"], "bob@example.org")
        self.assertEqual(output["daily_supervisor_assignment_source"], "semantic")

    def test_incompatible_preassignment_is_rejected(self) -> None:
        researchers = pd.DataFrame(
            [
                researcher(
                    "Alice",
                    "alice@example.org",
                    "privacy law",
                    languages="Dutch",
                    promotor_max=0,
                )
            ]
        )
        assignments = pd.DataFrame(
            [
                {
                    "full_name": "Student",
                    "email": "student@example.org",
                    "assigned_topic_id": "privacy",
                    "assigned_topic": "Privacy law",
                    "assigned_language": "English",
                    "daily_supervisor": "Alice",
                    "daily_supervisor_email": "alice@example.org",
                }
            ]
        )

        with self.assertRaises(InputValidationError) as raised:
            match_supervisors(
                assignments,
                researchers,
                self.topics,
                self.backend,
                roles=("daily_supervisor",),
            )

        self.assertIn("does not supervise in 'English'", str(raised.exception))

    def test_minimum_slots_take_priority_when_feasible(self) -> None:
        researchers = pd.DataFrame(
            [
                researcher(
                    "Alice Privacy",
                    "alice@example.org",
                    "privacy privacy rights",
                    daily_min=0,
                    daily_max=2,
                    promotor_max=0,
                ),
                researcher(
                    "Bob Other",
                    "bob@example.org",
                    "medieval history",
                    daily_min=1,
                    daily_max=2,
                    promotor_max=0,
                ),
            ]
        )
        assignments = pd.DataFrame(
            [
                {
                    "full_name": "Student One",
                    "email": "one@example.org",
                    "assigned_topic_id": "privacy",
                    "assigned_topic": "Privacy law",
                },
                {
                    "full_name": "Student Two",
                    "email": "two@example.org",
                    "assigned_topic_id": "privacy",
                    "assigned_topic": "Privacy law",
                },
            ]
        )

        result = match_supervisors(
            assignments,
            researchers,
            self.topics,
            self.backend,
            roles=("daily_supervisor",),
        )

        counts = result.assignments["daily_supervisor_email"].value_counts()
        self.assertEqual(counts["bob@example.org"], 1)
        self.assertEqual(counts["alice@example.org"], 1)

    def test_topic_submitter_has_priority_over_similarity_and_minimums(self) -> None:
        researchers = pd.DataFrame(
            [
                researcher(
                    "Alice Submitter",
                    "alice@example.org",
                    "medieval history",
                    daily_min=0,
                    daily_max=1,
                    promotor_max=0,
                ),
                researcher(
                    "Bob Semantic Match",
                    "bob@example.org",
                    "privacy law rights safeguards",
                    daily_min=1,
                    daily_max=1,
                    promotor_max=0,
                ),
            ]
        )
        topics = self.topics.copy()
        topics.loc[
            topics["topic_id"] == "privacy",
            "submitter_email",
        ] = "alice@example.org"
        assignments = pd.DataFrame(
            [
                {
                    "full_name": "Student Privacy",
                    "email": "privacy.student@example.org",
                    "assigned_topic_id": "privacy",
                    "assigned_topic": "Privacy law",
                }
            ]
        )

        result = match_supervisors(
            assignments,
            researchers,
            topics,
            self.backend,
            roles=("daily_supervisor",),
        )

        output = result.assignments.iloc[0]
        self.assertEqual(
            output["daily_supervisor_email"],
            "alice@example.org",
        )
        self.assertEqual(
            output["daily_supervisor_assignment_source"],
            "topic_submitter",
        )
        self.assertTrue(
            any("Bob Semantic Match (0/1)" in warning for warning in result.warnings)
        )

    def test_topic_submitter_priority_stops_at_maximum_capacity(self) -> None:
        researchers = pd.DataFrame(
            [
                researcher(
                    "Alice Submitter",
                    "alice@example.org",
                    "privacy law",
                    daily_max=1,
                    promotor_max=0,
                ),
                researcher(
                    "Bob Available",
                    "bob@example.org",
                    "privacy law",
                    daily_max=1,
                    promotor_max=0,
                ),
            ]
        )
        topics = pd.DataFrame(
            [
                {
                    "topic_id": "privacy-one",
                    "topic_title": "Privacy one",
                    "topic_description": "privacy law",
                    "submitter_email": "alice@example.org",
                    "capacity": 1,
                },
                {
                    "topic_id": "privacy-two",
                    "topic_title": "Privacy two",
                    "topic_description": "privacy law",
                    "submitter_email": "alice@example.org",
                    "capacity": 1,
                },
            ]
        )
        assignments = pd.DataFrame(
            [
                {
                    "full_name": "Student One",
                    "email": "one@example.org",
                    "assigned_topic_id": "privacy-one",
                    "assigned_topic": "Privacy one",
                },
                {
                    "full_name": "Student Two",
                    "email": "two@example.org",
                    "assigned_topic_id": "privacy-two",
                    "assigned_topic": "Privacy two",
                },
            ]
        )

        result = match_supervisors(
            assignments,
            researchers,
            topics,
            self.backend,
            roles=("daily_supervisor",),
        )

        counts = result.assignments["daily_supervisor_email"].value_counts()
        sources = result.assignments["daily_supervisor_assignment_source"]
        self.assertEqual(counts["alice@example.org"], 1)
        self.assertEqual(counts["bob@example.org"], 1)
        self.assertEqual((sources == "topic_submitter").sum(), 1)

    def test_departure_reassigns_only_affected_rows(self) -> None:
        researchers = pd.DataFrame(
            [
                researcher("Alice", "alice@example.org", "privacy law"),
                researcher("Bob", "bob@example.org", "data engineering"),
                researcher("Carol", "carol@example.org", "privacy governance"),
            ]
        )
        assignments = pd.DataFrame(
            [
                {
                    "full_name": "Student Privacy",
                    "email": "privacy.student@example.org",
                    "assigned_topic_id": "privacy",
                    "assigned_topic": "Privacy law",
                    "daily_supervisor": "Alice",
                    "daily_supervisor_email": "alice@example.org",
                    "promotor": "Bob",
                    "promotor_email": "bob@example.org",
                },
                {
                    "full_name": "Student Data",
                    "email": "data.student@example.org",
                    "assigned_topic_id": "data",
                    "assigned_topic": "Data engineering",
                    "daily_supervisor": "Bob",
                    "daily_supervisor_email": "bob@example.org",
                    "promotor": "Alice",
                    "promotor_email": "alice@example.org",
                },
            ]
        )

        result = reassign_supervision(
            assignments,
            researchers,
            self.topics,
            self.backend,
            role="daily_supervisor",
            departing_supervisor_email="alice@example.org",
        )

        output = result.assignments.set_index("email")
        self.assertEqual(
            output.at["privacy.student@example.org", "daily_supervisor_email"],
            "carol@example.org",
        )
        self.assertEqual(
            output.at["data.student@example.org", "daily_supervisor_email"],
            "bob@example.org",
        )
        self.assertEqual(len(result.log), 1)
        self.assertEqual(
            result.log.iloc[0]["previous_supervisor_email"],
            "alice@example.org",
        )
        self.assertEqual(
            result.log.iloc[0]["new_supervisor_email"],
            "carol@example.org",
        )


if __name__ == "__main__":
    unittest.main()
