"""Targeted reassignment after a departure or an ad hoc replacement."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from thesis_allocation.carryover import (
    augment_topics_with_carry_over,
    restore_carry_over_topic_display,
)
from thesis_allocation.errors import InputValidationError
from thesis_allocation.matching import (
    ROLE_SPECS,
    MatchResult,
    match_supervisors,
)
from thesis_allocation.schema import normalize_assignments, normalize_email
from thesis_allocation.similarity import SimilarityBackend


@dataclass(frozen=True)
class ReplacementResult:
    """Updated assignments, workload summary, and an auditable change log."""

    assignments: pd.DataFrame
    summary: pd.DataFrame
    log: pd.DataFrame
    warnings: tuple[str, ...] = ()


def reassign_supervision(
    assignments: pd.DataFrame,
    researchers: pd.DataFrame,
    topics: pd.DataFrame,
    backend: SimilarityBackend,
    *,
    role: str,
    student_email: str | None = None,
    departing_supervisor_email: str | None = None,
    allow_partial: bool = False,
    enforce_distinct_roles: bool = True,
) -> ReplacementResult:
    """Reassign one student's role or every assignment held by one departure."""

    if role not in ROLE_SPECS:
        raise InputValidationError(
            f"Unknown role '{role}'; use daily_supervisor or promotor"
        )
    if bool(student_email) == bool(departing_supervisor_email):
        raise InputValidationError(
            "Provide exactly one target: student_email or departing_supervisor_email"
        )

    original_assignments = assignments.copy()
    matching_topics = augment_topics_with_carry_over(assignments, topics)
    baseline: MatchResult = match_supervisors(
        assignments,
        researchers,
        matching_topics,
        backend,
        roles=(),
        allow_partial=True,
        enforce_distinct_roles=enforce_distinct_roles,
    )
    working = normalize_assignments(baseline.assignments)
    spec = ROLE_SPECS[role]

    excluded: set[str] = set()
    normalized_student = normalize_email(student_email)
    normalized_departure = normalize_email(departing_supervisor_email)
    if normalized_student:
        target_mask = working["email"].eq(normalized_student)
        if not target_mask.any():
            raise InputValidationError(
                f"Student email '{normalized_student}' was not found"
            )
        previous_emails = {
            normalize_email(value)
            for value in working.loc[target_mask, spec.email_column]
            if normalize_email(value)
        }
        excluded.update(previous_emails)
    else:
        target_mask = working[spec.email_column].map(normalize_email).eq(
            normalized_departure
        )
        if not target_mask.any():
            raise InputValidationError(
                f"No {spec.label.casefold()} assignment uses "
                f"'{normalized_departure}'"
            )
        excluded.add(normalized_departure)

    target_indices = working.index[target_mask].tolist()
    previous = working.loc[
        target_indices,
        ["email", spec.name_column, spec.email_column],
    ].copy()
    previous.columns = [
        "student_email",
        "previous_supervisor",
        "previous_supervisor_email",
    ]

    working.loc[target_mask, spec.name_column] = ""
    working.loc[target_mask, spec.email_column] = ""
    if spec.score_column in working.columns:
        working.loc[target_mask, spec.score_column] = pd.NA
    if spec.source_column in working.columns:
        working.loc[target_mask, spec.source_column] = ""

    target_students = set(working.loc[target_mask, "email"])
    updated = match_supervisors(
        working,
        researchers,
        matching_topics,
        backend,
        roles=(role,),
        allow_partial=allow_partial,
        enforce_distinct_roles=enforce_distinct_roles,
        excluded_researcher_emails=excluded,
        target_student_emails=target_students,
    )
    restored_assignments = restore_carry_over_topic_display(
        updated.assignments,
        original_assignments,
    )

    new_rows = restored_assignments.set_index("email")
    log = previous.copy()
    log["role"] = role
    log["new_supervisor"] = log["student_email"].map(
        new_rows[spec.name_column]
    )
    log["new_supervisor_email"] = log["student_email"].map(
        new_rows[spec.email_column]
    )
    log["match_score"] = log["student_email"].map(
        new_rows[spec.score_column]
    )
    log["assignment_source"] = log["student_email"].map(
        new_rows[spec.source_column]
    )
    log = log[
        [
            "student_email",
            "role",
            "previous_supervisor",
            "previous_supervisor_email",
            "new_supervisor",
            "new_supervisor_email",
            "match_score",
            "assignment_source",
        ]
    ]

    return ReplacementResult(
        assignments=restored_assignments,
        summary=updated.summary,
        log=log.reset_index(drop=True),
        warnings=updated.warnings,
    )
