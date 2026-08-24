"""Globally optimal allocation of ranked thesis topic preferences."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from thesis_allocation.errors import (
    InfeasibleAssignmentError,
    InputValidationError,
)
from thesis_allocation.flow import MinCostFlow
from thesis_allocation.languages import first_compatible_language
from thesis_allocation.schema import (
    OWN_TOPIC_ID,
    clean_text,
    normalize_preferences,
    normalize_topic_id,
    normalize_topics,
)


@dataclass(frozen=True)
class TopicAllocationResult:
    """Topic assignment output and run diagnostics."""

    assignments: pd.DataFrame
    total_cost: int
    assigned_count: int
    warnings: tuple[str, ...] = ()


class TopicResolver:
    """Resolve offered thesis topics by exact topic ID only."""

    def __init__(self, topics: pd.DataFrame):
        self.topics = topics
        self.lookup = {
            normalize_topic_id(row["topic_id"]): index
            for index, row in topics.iterrows()
        }

    def resolve(self, reference: object) -> int:
        """Return the topic row index for one exact topic ID."""

        topic_id = normalize_topic_id(reference)
        if not topic_id:
            raise InputValidationError("A blank topic ID cannot be resolved")
        if topic_id == OWN_TOPIC_ID:
            raise InputValidationError(
                f"Topic ID {OWN_TOPIC_ID} is reserved for a student's own topic"
            )
        try:
            return self.lookup[topic_id]
        except KeyError as exc:
            raise InputValidationError(
                f"Topic ID '{clean_text(reference)}' was not found in the topics file"
            ) from exc


def allocate_topics(
    preferences: pd.DataFrame,
    topics: pd.DataFrame,
    *,
    duplicate_policy: str = "keep-last",
    allow_partial: bool = False,
) -> TopicAllocationResult:
    """Allocate students to ranked topic IDs at the lowest total rank cost."""

    students = normalize_preferences(
        preferences,
        duplicate_policy=duplicate_policy,
    )
    topic_table = normalize_topics(topics)
    resolver = TopicResolver(topic_table)

    source = 0
    student_node_start = 1
    topic_node_start = student_node_start + len(students)
    sink = topic_node_start + len(topic_table)
    network = MinCostFlow(sink + 1)

    student_nodes = {
        email: student_node_start + offset
        for offset, email in enumerate(sorted(students["email"]))
    }
    topic_nodes = {
        topic_id: topic_node_start + offset
        for offset, topic_id in enumerate(sorted(topic_table["topic_id"]))
    }

    for email in sorted(student_nodes):
        network.add_edge(source, student_nodes[email], 1, 0)
    for _, topic in topic_table.sort_values("topic_id").iterrows():
        network.add_edge(
            topic_nodes[topic["topic_id"]],
            sink,
            int(topic["capacity"]),
            0,
        )

    issues: list[str] = []
    warnings: list[str] = []
    feasible_students: set[str] = set()

    for student_position, student in students.iterrows():
        email = student["email"]
        for rank in (1, 2, 3):
            reference = student[f"preference_{rank}"]
            topic_id = normalize_topic_id(reference)
            _, assigned_language = first_compatible_language(
                student[f"preference_{rank}_languages"],
                "",
            )

            if topic_id == OWN_TOPIC_ID:
                network.add_edge(
                    student_nodes[email],
                    sink,
                    1,
                    rank,
                    data={
                        "student_position": student_position,
                        "student_email": email,
                        "topic_id": OWN_TOPIC_ID,
                        "topic_title": "Own topic",
                        "own_topic_description": student["own_topic_description"],
                        "rank": rank,
                        "language": assigned_language,
                    },
                )
                feasible_students.add(email)
                continue

            try:
                topic_index = resolver.resolve(reference)
            except InputValidationError as exc:
                issues.extend(
                    f"student '{email}', preference {rank}: {issue}"
                    for issue in exc.issues
                )
                continue

            topic = topic_table.loc[topic_index]
            data = {
                "student_position": student_position,
                "student_email": email,
                "topic_id": topic["topic_id"],
                "topic_title": topic["topic_title"],
                "own_topic_description": "",
                "rank": rank,
                "language": assigned_language,
            }
            network.add_edge(
                student_nodes[email],
                topic_nodes[topic["topic_id"]],
                1,
                rank,
                data=data,
            )
            feasible_students.add(email)

    if issues:
        raise InputValidationError(issues)

    flow, total_cost = network.solve(source, sink, len(students))
    assignments_by_email = {
        edge.data["student_email"]: edge.data
        for edge in network.used_data_edges()
    }

    result = students.copy()
    result["assigned_topic_id"] = result["email"].map(
        lambda email: assignments_by_email.get(email, {}).get("topic_id")
    )
    result["assigned_topic"] = result["email"].map(
        lambda email: assignments_by_email.get(email, {}).get("topic_title")
    )
    result["own_topic_description"] = result["email"].map(
        lambda email: assignments_by_email.get(email, {}).get(
            "own_topic_description",
            clean_text(
                result.loc[result["email"].eq(email), "own_topic_description"].iloc[0]
            ),
        )
    )
    result["assigned_rank"] = result["email"].map(
        lambda email: assignments_by_email.get(email, {}).get("rank")
    ).astype("Int64")
    result["assigned_cost"] = result["assigned_rank"]
    result["assigned_language"] = result["email"].map(
        lambda email: assignments_by_email.get(email, {}).get("language")
    )

    unassigned = sorted(set(students["email"]) - set(assignments_by_email))
    if unassigned and not allow_partial:
        details: list[str] = []
        for email in unassigned:
            if email not in feasible_students:
                details.append(f"{email}: no valid topic-ID preference edge")
            else:
                details.append(f"{email}: all preferred offered topics reached capacity")
        raise InfeasibleAssignmentError(
            "A complete topic allocation is impossible. "
            f"Assigned {flow} of {len(students)} students.\n"
            + "\n".join(f"  - {detail}" for detail in details)
        )
    if unassigned:
        warnings.append(
            f"Partial allocation: {len(unassigned)} student(s) remain unassigned"
        )

    return TopicAllocationResult(
        assignments=result,
        total_cost=total_cost,
        assigned_count=flow,
        warnings=tuple(dict.fromkeys(warnings)),
    )
