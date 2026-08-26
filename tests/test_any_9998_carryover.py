from __future__ import annotations

import unittest

import pandas as pd

from thesis_allocation.carryover import (
    MANUAL_REVIEW_SOURCE,
    MANUAL_REVIEW_TEXT,
    allocate_annual_topics,
    finalize_manual_review_assignments,
)


class AnyPreferenceCarryOverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.topics = pd.DataFrame(
            [
                {
                    "topic_id": "current-a",
                    "topic_title": "Current A",
                    "topic_description": "current topic A",
                    "capacity": 5,
                },
                {
                    "topic_id": "current-b",
                    "topic_title": "Current B",
                    "topic_description": "current topic B",
                    "capacity": 5,
                },
            ]
        )
        self.researchers = pd.DataFrame(
            [
                {
                    "full_name": "Researcher",
                    "email": "researcher@example.org",
                    "supervision_languages": "English",
                    "profile_description": "research profile",
                    "daily_supervisor_minimum_theses": 0,
                    "daily_supervisor_maximum_theses": 1,
                    "promotor_minimum_theses": 0,
                    "promotor_maximum_theses": 1,
                }
            ]
        )
        self.previous = pd.DataFrame(
            [
                {
                    "full_name": "Carry Student",
                    "email": "carry@example.org",
                    "assigned_topic_id": "old-topic",
                    "assigned_topic": "Previous thesis",
                    "assigned_topic_description": "previous thesis description",
                    "assigned_language": "English",
                    "daily_supervisor": "",
                    "daily_supervisor_email": "",
                    "promotor": "",
                    "promotor_email": "",
                }
            ]
        )

    def _preferences(
        self,
        preference_1: object,
        preference_2: object,
        preference_3: object,
        *,
        own_topic_description: str = "",
    ) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "full_name": "Carry Student",
                    "email": "carry@example.org",
                    "preference_1": preference_1,
                    "preference_1_languages": "English",
                    "preference_2": preference_2,
                    "preference_2_languages": "English",
                    "preference_3": preference_3,
                    "preference_3_languages": "English",
                    "own_topic_description": own_topic_description,
                }
            ]
        )

    def test_9998_in_second_preference_is_carry_over(self) -> None:
        result = allocate_annual_topics(
            self._preferences("current-a", 9998, "current-b"),
            self.topics,
            self.researchers,
            self.previous,
        )

        row = result.assignments.iloc[0]
        self.assertEqual(result.carry_over_count, 1)
        self.assertEqual(result.assigned_count, 1)
        self.assertEqual(result.total_cost, 0)
        self.assertEqual(row["preference_1"], "current-a")
        self.assertEqual(row["preference_2"], "9998")
        self.assertEqual(row["preference_3"], "current-b")
        self.assertEqual(row["assigned_topic_id"], "old-topic")
        self.assertEqual(row["assigned_topic"], "Previous thesis")
        self.assertEqual(row["topic_assignment_source"], "carry_over")

    def test_9998_in_third_preference_is_carry_over(self) -> None:
        result = allocate_annual_topics(
            self._preferences("current-a", "current-b", 9998),
            self.topics,
            self.researchers,
            self.previous,
        )

        row = result.assignments.iloc[0]
        self.assertEqual(result.carry_over_count, 1)
        self.assertEqual(row["preference_3"], "9998")
        self.assertEqual(row["assigned_topic_id"], "old-topic")
        self.assertEqual(row["topic_assignment_source"], "carry_over")

    def test_9998_in_all_three_preferences_is_single_carry_over(self) -> None:
        result = allocate_annual_topics(
            self._preferences(9998, 9998, 9998),
            self.topics,
            self.researchers,
            self.previous,
        )

        row = result.assignments.iloc[0]
        self.assertEqual(result.carry_over_count, 1)
        self.assertEqual(result.assigned_count, 1)
        self.assertEqual(result.total_cost, 0)
        self.assertEqual(row["assigned_topic_id"], "old-topic")
        self.assertEqual(row["topic_assignment_source"], "carry_over")

    def test_9998_overrides_9999_on_same_row(self) -> None:
        result = allocate_annual_topics(
            self._preferences(9999, 9998, "current-b"),
            self.topics,
            self.researchers,
            self.previous,
        )

        row = result.assignments.iloc[0]
        self.assertEqual(result.carry_over_count, 1)
        self.assertEqual(result.total_cost, 0)
        self.assertEqual(row["preference_1"], "9999")
        self.assertEqual(row["preference_2"], "9998")
        self.assertEqual(row["assigned_topic_id"], "old-topic")
        self.assertEqual(row["assigned_topic"], "Previous thesis")
        self.assertEqual(row["topic_assignment_source"], "carry_over")

    def test_9998_in_later_preference_without_previous_file_needs_manual_review(self) -> None:
        result = allocate_annual_topics(
            self._preferences("current-a", 9998, "current-b"),
            self.topics,
            self.researchers,
            previous_final_assignments=None,
        )

        output = finalize_manual_review_assignments(result.assignments)
        row = output.iloc[0]
        self.assertEqual(result.carry_over_count, 1)
        self.assertEqual(result.manual_review_count, 1)
        self.assertEqual(result.assigned_count, 0)
        self.assertEqual(row["assigned_topic_id"], "9998")
        self.assertEqual(row["assigned_topic"], MANUAL_REVIEW_TEXT)
        self.assertEqual(row["topic_assignment_source"], MANUAL_REVIEW_SOURCE)


if __name__ == "__main__":
    unittest.main()
