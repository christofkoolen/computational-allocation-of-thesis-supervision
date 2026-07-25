"""Globally optimal allocation of ranked thesis topic preferences."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

import pandas as pd

from thesis_allocation.errors import (
    InfeasibleAssignmentError,
    InputValidationError,
)
from thesis_allocation.flow import MinCostFlow
from thesis_allocation.languages import first_compatible_language
from thesis_allocation.schema import (
    clean_text,
    normalize_preferences,
    normalize_topics,
    normalized_key,
)


@dataclass(frozen=True)
class TopicAllocationResult:
    """Topic assignment output and run diagnostics."""

    assignments: pd.DataFrame
    total_cost: int
    assigned_count: int
    warnings: tuple[str, ...] = ()


class TopicResolver:
    """Resolve topic IDs or titles with guarded fuzzy matching."""

    def __init__(
        self,
        topics: pd.DataFrame,
        *,
        fuzzy_threshold: float = 0.90,
        fuzzy_margin: float = 0.05,
    ):
        self.topics = topics
        self.fuzzy_threshold = fuzzy_threshold
        self.fuzzy_margin = fuzzy_margin
        self.lookup: dict[str, set[int]] = {}
        for index, row in topics.iterrows():
            for value in (row["topic_id"], row["topic_title"]):
                key = normalized_key(value)
                self.lookup.setdefault(key, set()).add(index)

    def resolve(self, reference: object) -> tuple[int, bool]:
        """Return a topic row index and whether fuzzy matching was used."""

        key = normalized_key(reference)
        if not key:
            raise InputValidationError("A blank topic reference cannot be resolved")

        exact = self.lookup.get(key, set())
        if len(exact) == 1:
            return next(iter(exact)), False
        if len(exact) > 1:
            raise InputValidationError(
                f"Topic reference '{clean_text(reference)}' is ambiguous"
            )

        topic_scores: dict[int, float] = {}
        for candidate, indices in self.lookup.items():
            score = SequenceMatcher(None, key, candidate).ratio()
            for index in indices:
                topic_scores[index] = max(topic_scores.get(index, 0.0), score)
        scored_topics = sorted(
            ((score, index) for index, score in topic_scores.items()),
            reverse=True,
        )
        if not scored_topics:
            raise InputValidationError(
                f"Topic reference '{clean_text(reference)}' was not found"
            )
        best_score, best_index = scored_topics[0]
        second_score = scored_topics[1][0] if len(scored_topics) > 1 else 0.0
        if (
            best_score >= self.fuzzy_threshold
            and best_score - second_score >= self.fuzzy_margin
        ):
            return best_index, True

        suggestions = [
            self.topics.at[index, "topic_title"]
            for _, index in scored_topics[:3]
        ]
        suffix = f" Closest topics: {', '.join(suggestions)}." if suggestions else ""
        raise InputValidationError(
            f"Topic reference '{clean_text(reference)}' was not found unambiguously."
            f"{suffix}"
        )


def allocate_topics(
    preferences: pd.DataFrame,
    topics: pd.DataFrame,
    *,
    duplicate_policy: str = "keep-last",
    allow_partial: bool = False,
    fuzzy_threshold: float = 0.90,
    fuzzy_margin: float = 0.05,
) -> TopicAllocationResult:
    """Allocate students to ranked choices at the lowest possible total rank cost."""

    students = normalize_preferences(
        preferences,
        duplicate_policy=duplicate_policy,
    )
    topic_table = normalize_topics(topics)
    resolver = TopicResolver(
        topic_table,
        fuzzy_threshold=fuzzy_threshold,
        fuzzy_margin=fuzzy_margin,
    )

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
    blocked_by_language: dict[str, list[str]] = {}
    feasible_students: set[str] = set()

    for student_position, student in students.iterrows():
        email = student["email"]
        resolved_for_student: set[str] = set()
        for rank in (1, 2, 3):
            reference = student[f"preference_{rank}"]
            if not reference:
                continue
            try:
                topic_index, fuzzy = resolver.resolve(reference)
            except InputValidationError as exc:
                issues.extend(
                    f"student '{email}', preference {rank}: {issue}"
                    for issue in exc.issues
                )
                continue

            topic = topic_table.loc[topic_index]
            topic_id = topic["topic_id"]
            if topic_id in resolved_for_student:
                continue
            if fuzzy:
                warnings.append(
                    f"Fuzzy-matched '{reference}' to '{topic['topic_title']}' "
                    f"for student '{email}'"
                )

            compatible, assigned_language = first_compatible_language(
                student[f"preference_{rank}_languages"],
                topic["supervision_languages"],
            )
            if not compatible:
                blocked_by_language.setdefault(email, []).append(
                    f"{topic['topic_title']} (preference {rank})"
                )
                continue

            resolved_for_student.add(topic_id)
            data = {
                "student_position": student_position,
                "student_email": email,
                "topic_id": topic_id,
                "topic_title": topic["topic_title"],
                "rank": rank,
                "language": assigned_language,
            }
            network.add_edge(
                student_nodes[email],
                topic_nodes[topic_id],
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
                blocked = blocked_by_language.get(email, [])
                if blocked:
                    details.append(
                        f"{email}: no language-compatible choice "
                        f"({'; '.join(blocked)})"
                    )
                else:
                    details.append(f"{email}: no valid preference edge")
            else:
                details.append(f"{email}: all preferred topics reached capacity")
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
