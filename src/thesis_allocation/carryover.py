"""Carry previous-year thesis allocations into a new annual allocation run."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from thesis_allocation.errors import InputValidationError
from thesis_allocation.languages import first_compatible_language
from thesis_allocation.schema import (
    CARRY_OVER_TOPIC_ID,
    OWN_TOPIC_ID,
    clean_text,
    normalize_assignments,
    normalize_email,
    normalize_preferences,
    normalize_researchers,
    normalize_topic_id,
    normalize_topics,
    normalized_key,
)
from thesis_allocation.topics import allocate_topics


MANUAL_REVIEW_TEXT = "CARRY-OVER STUDENT - MANUAL REVIEW NEEDED"
MANUAL_REVIEW_SOURCE = "carry_over_manual_review"
MANUAL_REVIEW_ROLE_SOURCE = "manual_review"
MANUAL_REVIEW_TOPIC_PREFIX = "manual-carry-over:"

ROLE_COLUMNS = {
    "daily_supervisor": {
        "label": "Daily supervisor",
        "name": "daily_supervisor",
        "email": "daily_supervisor_email",
        "maximum": "daily_supervisor_maximum_theses",
        "score": "daily_supervisor_match_score",
        "source": "daily_supervisor_assignment_source",
    },
    "promotor": {
        "label": "Promotor",
        "name": "promotor",
        "email": "promotor_email",
        "maximum": "promotor_maximum_theses",
        "score": "promotor_match_score",
        "source": "promotor_assignment_source",
    },
}


@dataclass(frozen=True)
class AnnualTopicAllocationResult:
    """Combined new and previous-year topic assignments for an annual run."""

    assignments: pd.DataFrame
    matching_topics: pd.DataFrame
    total_cost: int
    assigned_count: int
    carry_over_count: int
    manual_review_count: int
    warnings: tuple[str, ...] = ()


def _researcher_maps(
    researchers: pd.DataFrame,
) -> tuple[dict[str, pd.Series], dict[str, list[pd.Series]]]:
    by_email = {row["email"]: row for _, row in researchers.iterrows()}
    by_name: dict[str, list[pd.Series]] = {}
    for _, row in researchers.iterrows():
        by_name.setdefault(normalized_key(row["full_name"]), []).append(row)
    return by_email, by_name


def _resolve_carry_over_role(
    previous: pd.Series,
    researchers_by_email: dict[str, pd.Series],
    researchers_by_name: dict[str, list[pd.Series]],
    *,
    role: str,
    assigned_language: str,
    student_email: str,
) -> tuple[str, str, str | None]:
    spec = ROLE_COLUMNS[role]
    supplied_email = normalize_email(previous.get(spec["email"]))
    supplied_name = clean_text(previous.get(spec["name"]))
    if not supplied_email and not supplied_name:
        return "", "", None

    candidate: pd.Series | None = None
    if supplied_email:
        candidate = researchers_by_email.get(supplied_email)
        if candidate is None:
            return (
                "",
                "",
                f"Carry-over student '{student_email}': previous "
                f"{spec['label'].casefold()} '{supplied_email}' is not in the current "
                "researchers file and will be reassigned",
            )
    else:
        matches = researchers_by_name.get(normalized_key(supplied_name), [])
        if not matches:
            return (
                "",
                "",
                f"Carry-over student '{student_email}': previous "
                f"{spec['label'].casefold()} '{supplied_name}' is not in the current "
                "researchers file and will be reassigned",
            )
        if len(matches) > 1:
            raise InputValidationError(
                f"Carry-over student '{student_email}' has ambiguous previous "
                f"{spec['label'].casefold()} name '{supplied_name}'; provide the email "
                "in previous_final_assignments"
            )
        candidate = matches[0]

    if supplied_name and normalized_key(supplied_name) != normalized_key(
        candidate["full_name"]
    ):
        raise InputValidationError(
            f"Carry-over student '{student_email}' has conflicting previous "
            f"{spec['label'].casefold()} name and email"
        )

    if int(candidate[spec["maximum"]]) <= 0:
        return (
            "",
            "",
            f"Carry-over student '{student_email}': previous "
            f"{spec['label'].casefold()} '{candidate['email']}' is no longer eligible "
            "for that role and will be reassigned",
        )

    compatible, _ = first_compatible_language(
        assigned_language,
        candidate["supervision_languages"],
    )
    if not compatible:
        return (
            "",
            "",
            f"Carry-over student '{student_email}': previous "
            f"{spec['label'].casefold()} '{candidate['email']}' does not supervise in "
            f"'{assigned_language}' and will be reassigned",
        )

    return candidate["full_name"], candidate["email"], None


def _release_excess_carry_over_capacity(
    assignments: pd.DataFrame,
    researchers: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    """Keep carry-over roles only up to each researcher's current maximum."""

    if assignments.empty:
        return assignments, []

    result = assignments.copy()
    researcher_table = researchers.set_index("email")
    warnings: list[str] = []
    for spec in ROLE_COLUMNS.values():
        assigned_emails = result[spec["email"]].map(normalize_email)
        for researcher_email in sorted(
            email for email in assigned_emails.unique() if email
        ):
            indices = result.index[assigned_emails.eq(researcher_email)].tolist()
            maximum = int(researcher_table.at[researcher_email, spec["maximum"]])
            if len(indices) <= maximum:
                continue
            for index in indices[maximum:]:
                student_email = result.at[index, "email"]
                result.at[index, spec["name"]] = ""
                result.at[index, spec["email"]] = ""
                result.at[index, spec["score"]] = pd.NA
                result.at[index, spec["source"]] = ""
                warnings.append(
                    f"Carry-over student '{student_email}': previous "
                    f"{spec['label'].casefold()} '{researcher_email}' exceeds that "
                    "researcher's current maximum capacity and will be reassigned"
                )
    return result, warnings


def _manual_review_row(student: pd.Series) -> dict[str, object]:
    """Create a non-matchable placeholder row for unresolved topic 9998."""

    email = normalize_email(student.get("email"))
    row = student.to_dict()
    row["assigned_topic_id"] = f"{MANUAL_REVIEW_TOPIC_PREFIX}{email}"
    row["assigned_topic"] = MANUAL_REVIEW_TEXT
    row["assigned_topic_description"] = MANUAL_REVIEW_TEXT
    row["own_topic_description"] = clean_text(row.get("own_topic_description"))
    row["assigned_rank"] = pd.NA
    row["assigned_cost"] = pd.NA
    row["assigned_language"] = MANUAL_REVIEW_TEXT
    row["topic_assignment_source"] = MANUAL_REVIEW_SOURCE
    for spec in ROLE_COLUMNS.values():
        row[spec["name"]] = ""
        row[spec["email"]] = ""
        row[spec["score"]] = pd.NA
        row[spec["source"]] = MANUAL_REVIEW_ROLE_SOURCE
    return row


def finalize_manual_review_assignments(assignments: pd.DataFrame) -> pd.DataFrame:
    """Expose unresolved carry-over rows clearly without inventing identifiers."""

    result = assignments.copy()
    if "topic_assignment_source" not in result.columns:
        return result
    manual = result["topic_assignment_source"].map(clean_text).str.casefold().eq(
        MANUAL_REVIEW_SOURCE
    )
    if not manual.any():
        return result

    result.loc[manual, "assigned_topic_id"] = CARRY_OVER_TOPIC_ID
    for column in (
        "assigned_topic",
        "assigned_topic_description",
        "assigned_language",
        "daily_supervisor",
        "promotor",
    ):
        if column in result.columns:
            result.loc[manual, column] = MANUAL_REVIEW_TEXT
    for column in ("daily_supervisor_email", "promotor_email"):
        if column in result.columns:
            result.loc[manual, column] = ""
    for column in (
        "daily_supervisor_match_score",
        "promotor_match_score",
    ):
        if column in result.columns:
            result.loc[manual, column] = pd.NA
    for column in (
        "daily_supervisor_assignment_source",
        "promotor_assignment_source",
    ):
        if column in result.columns:
            result.loc[manual, column] = MANUAL_REVIEW_ROLE_SOURCE
    return result


def allocate_annual_topics(
    preferences: pd.DataFrame,
    topics: pd.DataFrame,
    researchers: pd.DataFrame,
    previous_final_assignments: pd.DataFrame | None = None,
    *,
    duplicate_policy: str = "keep-last",
    allow_partial: bool = False,
) -> AnnualTopicAllocationResult:
    """Allocate new topics while carrying forward students who select topic 9998."""

    students = normalize_preferences(
        preferences,
        duplicate_policy=duplicate_policy,
        allow_carry_over=True,
    )
    students = students.copy()
    students["_annual_order"] = range(len(students))
    topic_table = normalize_topics(topics)
    researcher_table = normalize_researchers(researchers, require_capacities=True)

    carry_mask = students["preference_1"].eq(CARRY_OVER_TOPIC_ID)
    carry_students = students.loc[carry_mask].copy()
    new_students = students.loc[~carry_mask].copy()

    new_allocation = allocate_topics(
        new_students,
        topic_table,
        duplicate_policy="error",
        allow_partial=allow_partial,
    )
    new_assignments = new_allocation.assignments.copy()
    new_assignments["topic_assignment_source"] = "ranked_preference"

    warnings: list[str] = list(new_allocation.warnings)
    carry_rows: list[dict[str, object]] = []
    manual_review_count = 0

    if not carry_students.empty and previous_final_assignments is None:
        carry_rows.extend(
            _manual_review_row(student)
            for _, student in carry_students.iterrows()
        )
        manual_review_count = len(carry_students)
        emails = ", ".join(carry_students["email"].tolist())
        warnings.append(
            f"Topic ID {CARRY_OVER_TOPIC_ID} was selected but "
            "previous_final_assignments was not provided. The run continued and "
            f"{manual_review_count} carry-over student(s) were marked for manual "
            f"review with automatic supervisor matching skipped: {emails}"
        )

    elif not carry_students.empty:
        previous_table = normalize_assignments(previous_final_assignments)
        previous_by_email = previous_table.set_index("email", drop=False)
        missing = [
            email
            for email in carry_students["email"]
            if email not in previous_by_email.index
        ]
        if missing:
            raise InputValidationError(
                f"Topic ID {CARRY_OVER_TOPIC_ID} was selected, but no previous final "
                f"assignment was found for student(s): {', '.join(missing)}"
            )

        researchers_by_email, researchers_by_name = _researcher_maps(researcher_table)
        issues: list[str] = []
        for _, student in carry_students.iterrows():
            email = student["email"]
            previous = previous_by_email.loc[email]
            previous_topic_id = normalize_topic_id(previous.get("assigned_topic_id"))
            previous_topic_title = clean_text(previous.get("assigned_topic"))
            if not previous_topic_id:
                issues.append(
                    f"Carry-over student '{email}' has no assigned_topic_id in "
                    "previous_final_assignments"
                )
                continue
            if previous_topic_id == CARRY_OVER_TOPIC_ID:
                issues.append(
                    f"Carry-over student '{email}' has reserved topic ID "
                    f"{CARRY_OVER_TOPIC_ID} as a previous assigned topic"
                )
                continue
            if not previous_topic_title:
                issues.append(
                    f"Carry-over student '{email}' has no assigned_topic in "
                    "previous_final_assignments"
                )
                continue

            assigned_language = clean_text(previous.get("assigned_language"))
            previous_description = clean_text(
                previous.get("assigned_topic_description")
            )
            previous_own_description = clean_text(
                previous.get("own_topic_description")
            )
            if not previous_description and previous_topic_id == OWN_TOPIC_ID:
                previous_description = previous_own_description

            row = student.to_dict()
            row["assigned_topic_id"] = previous_topic_id
            row["assigned_topic"] = previous_topic_title
            row["assigned_topic_description"] = previous_description
            row["own_topic_description"] = previous_own_description
            row["assigned_rank"] = pd.NA
            row["assigned_cost"] = pd.NA
            row["assigned_language"] = assigned_language
            row["topic_assignment_source"] = "carry_over"

            for role, spec in ROLE_COLUMNS.items():
                name, role_email, warning = _resolve_carry_over_role(
                    previous,
                    researchers_by_email,
                    researchers_by_name,
                    role=role,
                    assigned_language=assigned_language,
                    student_email=email,
                )
                row[spec["name"]] = name
                row[spec["email"]] = role_email
                row[spec["score"]] = pd.NA
                row[spec["source"]] = "carry_over" if role_email else ""
                if warning:
                    warnings.append(warning)
            carry_rows.append(row)

        if issues:
            raise InputValidationError(issues)

    carry_assignments = pd.DataFrame(carry_rows)
    carry_assignments, capacity_warnings = _release_excess_carry_over_capacity(
        carry_assignments,
        researcher_table,
    )
    warnings.extend(capacity_warnings)

    parts = [frame for frame in (new_assignments, carry_assignments) if not frame.empty]
    if parts:
        combined = pd.concat(parts, ignore_index=True, sort=False)
        combined = combined.sort_values("_annual_order").reset_index(drop=True)
    else:
        combined = students.copy()
    combined = combined.drop(columns=["_annual_order"], errors="ignore")

    matching_topics = augment_topics_with_carry_over(combined, topic_table)
    return AnnualTopicAllocationResult(
        assignments=combined,
        matching_topics=matching_topics,
        total_cost=new_allocation.total_cost,
        assigned_count=(
            new_allocation.assigned_count
            + len(carry_assignments)
            - manual_review_count
        ),
        carry_over_count=len(carry_assignments),
        manual_review_count=manual_review_count,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def augment_topics_with_carry_over(
    assignments: pd.DataFrame,
    topics: pd.DataFrame,
) -> pd.DataFrame:
    """Add internal topic rows for compatibility with older matching paths."""

    topic_table = normalize_topics(topics)
    assignment_table = normalize_assignments(assignments)
    if "topic_assignment_source" not in assignment_table.columns:
        return topic_table

    source = assignment_table["topic_assignment_source"].map(clean_text).str.casefold()
    carry = assignment_table[
        source.isin({"carry_over", MANUAL_REVIEW_SOURCE})
    ]
    if carry.empty:
        return topic_table

    existing_ids = set(topic_table["topic_id"])
    existing_titles = {normalized_key(value) for value in topic_table["topic_title"]}
    synthetic: list[dict[str, object]] = []
    seen: set[str] = set()
    for _, row in carry.iterrows():
        topic_id = normalize_topic_id(row["assigned_topic_id"])
        if (
            not topic_id
            or topic_id == OWN_TOPIC_ID
            or topic_id in existing_ids
            or topic_id in seen
        ):
            continue
        title = f"Carry-over topic {topic_id}"
        suffix = 2
        while normalized_key(title) in existing_titles:
            title = f"Carry-over topic {topic_id} ({suffix})"
            suffix += 1
        existing_titles.add(normalized_key(title))
        seen.add(topic_id)
        description = clean_text(row.get("assigned_topic_description"))
        original_title = clean_text(row["assigned_topic"])
        topic_description = " ".join(
            part for part in (original_title, description) if part
        )
        synthetic.append(
            {
                "topic_id": topic_id,
                "topic_title": title,
                "topic_description": topic_description,
                "submitter_email": "",
                "capacity": 1,
            }
        )

    if not synthetic:
        return topic_table
    return pd.concat(
        [topic_table, pd.DataFrame(synthetic)],
        ignore_index=True,
        sort=False,
    )


def restore_carry_over_topic_display(
    assignments: pd.DataFrame,
    original_assignments: pd.DataFrame,
) -> pd.DataFrame:
    """Restore previous topic fields after carry-over supervision matching."""

    result = assignments.copy()
    original = normalize_assignments(original_assignments)
    if "topic_assignment_source" not in original.columns:
        return result
    carry = original[
        original["topic_assignment_source"].map(clean_text).str.casefold().eq(
            "carry_over"
        )
    ]
    if carry.empty:
        return result

    carry_by_email = carry.set_index("email")
    for index, row in result.iterrows():
        email = normalize_email(row.get("email"))
        if email not in carry_by_email.index:
            continue
        source = carry_by_email.loc[email]
        result.at[index, "assigned_topic_id"] = source["assigned_topic_id"]
        result.at[index, "assigned_topic"] = source["assigned_topic"]
        result.at[index, "assigned_topic_description"] = source[
            "assigned_topic_description"
        ]
        result.at[index, "own_topic_description"] = source["own_topic_description"]
    return result
