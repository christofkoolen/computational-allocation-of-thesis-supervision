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
                },
                {
                    "topic_id": "B",
                    "topic_title": "Beta",
                    "capacity": 1,
                },
                {
                    "topic_id": "C",
                    "topic_title": "Gamma",
                    "capacity": 1,
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

    def test_repeated_topic_ids_are_allowed_and_earliest_rank_wins(self) -> None:
        preferences = pd.DataFrame(
            [
                {
                    "full_name": "Student",
                    "email": "student@example.org",
                    "preference_1": "A",
                    "preference_2": "A",
                    "preference_3": "B",
                }
            ]
        )

        result = allocate_topics(preferences, self.topics)
        assignment = result.assignments.iloc[0]

        self.assertEqual(assignment["assigned_topic_id"], "A")
        self.assertEqual(assignment["assigned_rank"], 1)
        self.assertEqual(assignment["assigned_cost"], 1)

    def test_topic_allocation_carries_selected_supervision_language(self) -> None:
        preferences = pd.DataFrame(
            [
                {
                    "full_name": "Student",
                    "email": "student@example.org",
                    "preference_1": "A",
                    "preference_1_languages": "Dutch; English",
                    "preference_2": "B",
                    "preference_2_languages": "English",
                    "preference_3": "C",
                    "preference_3_languages": "English",
                }
            ]
        )

        result = allocate_topics(preferences, self.topics)
        assignment = result.assignments.iloc[0]

        self.assertEqual(assignment["assigned_topic_id"], "A")
        self.assertEqual(assignment["assigned_rank"], 1)
        self.assertEqual(assignment["assigned_language"], "Dutch")

    def test_title_is_not_accepted_in_place_of_topic_id(self) -> None:
        preferences = pd.DataFrame(
            [
                {
                    "full_name": "Student",
                    "email": "student@example.org",
                    "preference_1": "Alpha",
                    "preference_2": "B",
                    "preference_3": "C",
                }
            ]
        )

        with self.assertRaises(InputValidationError) as raised:
            allocate_topics(preferences, self.topics)

        self.assertIn("Topic ID 'Alpha' was not found", str(raised.exception))

    def test_unknown_topic_id_stops_without_fuzzy_matching(self) -> None:
        preferences = pd.DataFrame(
            [
                {
                    "full_name": "Student",
                    "email": "student@example.org",
                    "preference_1": "A-typo",
                    "preference_2": "B",
                    "preference_3": "C",
                }
            ]
        )

        with self.assertRaises(InputValidationError) as raised:
            allocate_topics(preferences, self.topics)

        self.assertIn("Topic ID 'A-typo' was not found", str(raised.exception))

    def test_own_topic_requires_description(self) -> None:
        preferences = pd.DataFrame(
            [
                {
                    "full_name": "Student",
                    "email": "student@example.org",
                    "preference_1": 9999,
                    "preference_2": "A",
                    "preference_3": "B",
                }
            ]
        )

        with self.assertRaises(InputValidationError) as raised:
            allocate_topics(preferences, self.topics)

        self.assertIn("own_topic_description", str(raised.exception))

    def test_own_topic_is_student_specific_and_keeps_description(self) -> None:
        preferences = pd.DataFrame(
            [
                {
                    "full_name": "Student",
                    "email": "student@example.org",
                    "preference_1": 9999,
                    "preference_2": "A",
                    "preference_3": "B",
                    "own_topic_description": "AI-assisted access to justice",
                }
            ]
        )

        result = allocate_topics(preferences, self.topics)
        assignment = result.assignments.iloc[0]

        self.assertEqual(assignment["assigned_topic_id"], "9999")
        self.assertEqual(assignment["assigned_topic"], "Own topic")
        self.assertEqual(
            assignment["own_topic_description"],
            "AI-assisted access to justice",
        )


if __name__ == "__main__":
    unittest.main()