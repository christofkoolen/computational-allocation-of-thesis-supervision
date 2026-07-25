from __future__ import annotations

import unittest

import pandas as pd

from thesis_allocation.errors import InputValidationError
from thesis_allocation.topics import allocate_topics


class TopicAllocationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.topics = pd.DataFrame(
            [
                {
                    "topic_id": "A",
                    "topic_title": "Alpha",
                    "capacity": 1,
                    "supervision_languages": "English",
                },
                {
                    "topic_id": "B",
                    "topic_title": "Beta",
                    "capacity": 1,
                    "supervision_languages": "English; Dutch",
                },
                {
                    "topic_id": "C",
                    "topic_title": "Gamma",
                    "capacity": 1,
                    "supervision_languages": "English",
                },
            ]
        )

    def test_finds_global_minimum_preference_cost(self) -> None:
        preferences = pd.DataFrame(
            [
                {
                    "full_name": "Student One",
                    "email": "one@example.org",
                    "preference_1": "A",
                    "preference_2": "B",
                    "preference_3": "C",
                },
                {
                    "full_name": "Student Two",
                    "email": "two@example.org",
                    "preference_1": "A",
                    "preference_2": "B",
                    "preference_3": "C",
                },
                {
                    "full_name": "Student Three",
                    "email": "three@example.org",
                    "preference_1": "B",
                    "preference_2": "A",
                    "preference_3": "C",
                },
            ]
        )

        result = allocate_topics(preferences, self.topics)

        self.assertEqual(result.assigned_count, 3)
        self.assertEqual(result.total_cost, 5)
        self.assertEqual(set(result.assignments["assigned_topic_id"]), {"A", "B", "C"})
        self.assertEqual(result.assignments["assigned_cost"].sum(), 5)

    def test_language_compatibility_is_part_of_the_optimization(self) -> None:
        preferences = pd.DataFrame(
            [
                {
                    "full_name": "Student",
                    "email": "student@example.org",
                    "preference_1": "A",
                    "preference_1_languages": "Dutch",
                    "preference_2": "B",
                    "preference_2_languages": "Dutch",
                }
            ]
        )

        result = allocate_topics(preferences, self.topics)
        assignment = result.assignments.iloc[0]

        self.assertEqual(assignment["assigned_topic_id"], "B")
        self.assertEqual(assignment["assigned_rank"], 2)
        self.assertEqual(assignment["assigned_language"], "Dutch")

    def test_guarded_fuzzy_matching_reports_use(self) -> None:
        preferences = pd.DataFrame(
            [
                {
                    "full_name": "Student",
                    "email": "student@example.org",
                    "preference_1": "Alphaa",
                }
            ]
        )

        result = allocate_topics(
            preferences,
            self.topics,
            fuzzy_threshold=0.80,
        )

        self.assertEqual(result.assignments.iloc[0]["assigned_topic_id"], "A")
        self.assertTrue(any("Fuzzy-matched" in warning for warning in result.warnings))

    def test_unknown_topic_stops_with_suggestions(self) -> None:
        preferences = pd.DataFrame(
            [
                {
                    "full_name": "Student",
                    "email": "student@example.org",
                    "preference_1": "Completely unrelated",
                }
            ]
        )

        with self.assertRaises(InputValidationError) as raised:
            allocate_topics(preferences, self.topics)

        self.assertIn("Closest topics", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

