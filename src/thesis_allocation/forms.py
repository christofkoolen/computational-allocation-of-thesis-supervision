"""Normalize the branching student-preference submission table."""

from __future__ import annotations

from hashlib import sha1

import pandas as pd

from thesis_allocation.errors import InputValidationError
from thesis_allocation.languages import parse_languages
from thesis_allocation.schema import clean_text, normalize_email, normalize_topic_id


FORM_MARKER_COLUMNS = {"thesis_type", "thesis_allocation_status"}
ALLOCATION_PATHS = ("ranked", "self_proposed", "carry_over")


def is_forms_export(frame: pd.DataFrame) -> bool:
    """Return whether a table uses the branching preference contract."""

    return FORM_MARKER_COLUMNS.issubset(
        {clean_text(column).casefold() for column in frame.columns}
    )


def _route(value: object, *, row_number: int) -> str:
    text = clean_text(value).casefold()
    if text.startswith("new topic"):
        return "ranked"
    if text.startswith("self-proposed topic") or text.startswith("self proposed topic"):
        return "self_proposed"
    if text.startswith("carry-over topic") or text.startswith("carry over topic"):
        return "carry_over"
    raise InputValidationError(
        f"spreadsheet row {row_number}: unknown thesis_allocation_status "
        f"'{clean_text(value)}'"
    )


def _submission_type(value: object, *, row_number: int) -> str:
    text = clean_text(value).casefold()
    if text.startswith("individual thesis"):
        return "individual"
    if text.startswith("dual thesis"):
        return "dual"
    raise InputValidationError(
        f"spreadsheet row {row_number}: unknown thesis_type '{clean_text(value)}'"
    )


def _group_id(member_emails: list[str]) -> str:
    key = "|".join(sorted(member_emails))
    return "thesis-" + sha1(key.encode("utf-8")).hexdigest()[:12]


def normalize_forms_submissions(
    frame: pd.DataFrame,
    *,
    duplicate_policy: str = "keep-last",
) -> pd.DataFrame:
    """Validate branching preferences and return one row per thesis group.

    A dual submission stays one allocation unit. Member details are retained in
    separate primary and partner columns so the final result can be expanded to
    one row per student without consuming topic or supervisor capacity twice.
    """

    if duplicate_policy not in {"error", "keep-first", "keep-last"}:
        raise ValueError("duplicate_policy must be error, keep-first, or keep-last")

    result = frame.copy()
    result.columns = [clean_text(column) for column in result.columns]
    if result.empty:
        raise InputValidationError("student_preferences contains no submissions")
    required_columns = {
        "full_name",
        "email",
        "student_number",
        "thesis_type",
        "thesis_allocation_status",
    }
    missing = sorted(required_columns - set(result.columns))
    if missing:
        raise InputValidationError(
            "student_preferences is missing required column(s): "
            + ", ".join(missing)
        )

    for column in (
        "partner_full_name",
        "partner_email",
        "partner_student_number",
        "dual_thesis_confirmation",
        "topic_preference_1",
        "topic_preference_1_languages",
        "topic_preference_2",
        "topic_preference_2_languages",
        "topic_preference_3",
        "topic_preference_3_languages",
        "self_proposed_thesis_title",
        "self_proposed_thesis_description",
        "self_proposed_thesis_language",
        "carry_over_thesis_topic",
        "carry_over_thesis_description",
        "carry_over_thesis_language",
        "daily_supervisor_email",
        "thesis_promotor_email",
    ):
        if column not in result.columns:
            result[column] = ""

    rows: list[dict[str, object]] = []
    issues: list[str] = []
    for index, source in result.iterrows():
        row_number = index + 2
        full_name = clean_text(source["full_name"])
        email = normalize_email(source["email"])
        student_number = clean_text(source["student_number"])
        try:
            submission_type = _submission_type(source["thesis_type"], row_number=row_number)
            allocation_path = _route(
                source["thesis_allocation_status"], row_number=row_number
            )
        except InputValidationError as exc:
            issues.extend(exc.issues)
            continue

        for field, value in (
            ("full_name", full_name),
            ("email", email),
            ("student_number", student_number),
        ):
            if not value:
                issues.append(f"spreadsheet row {row_number}: '{field}' is required")

        partner_name = clean_text(source["partner_full_name"])
        partner_email = normalize_email(source["partner_email"])
        partner_number = clean_text(source["partner_student_number"])
        confirmation = clean_text(source["dual_thesis_confirmation"])
        member_emails = [email]
        if submission_type == "dual":
            for field, value in (
                ("partner_full_name", partner_name),
                ("partner_email", partner_email),
                ("partner_student_number", partner_number),
                ("dual_thesis_confirmation", confirmation),
            ):
                if not value:
                    issues.append(
                        f"spreadsheet row {row_number}: '{field}' is required for a dual thesis"
                    )
            if partner_email and partner_email == email:
                issues.append(
                    f"spreadsheet row {row_number}: primary and partner email must differ"
                )
            if partner_email:
                member_emails.append(partner_email)
        else:
            partner_name = ""
            partner_email = ""
            partner_number = ""

        normalized = source.to_dict()
        normalized.update(
            {
                "full_name": full_name,
                "email": email,
                "student_number": student_number,
                "partner_full_name": partner_name,
                "partner_email": partner_email,
                "partner_student_number": partner_number,
                "submission_type": submission_type,
                "allocation_path": allocation_path,
                "group_size": 2 if submission_type == "dual" else 1,
                "thesis_group_id": _group_id(member_emails),
                "_form_order": index,
            }
        )

        if allocation_path == "ranked":
            choices: list[str] = []
            for rank in (1, 2, 3):
                topic_column = f"topic_preference_{rank}"
                language_column = f"topic_preference_{rank}_languages"
                topic_id = normalize_topic_id(source[topic_column])
                languages = parse_languages(source[language_column])
                normalized[topic_column] = topic_id
                normalized[language_column] = "; ".join(languages)
                if not topic_id:
                    issues.append(
                        f"spreadsheet row {row_number}: '{topic_column}' is required"
                    )
                if not languages:
                    issues.append(
                        f"spreadsheet row {row_number}: '{language_column}' is required"
                    )
                choices.append(topic_id)
            if len({choice for choice in choices if choice}) != 3:
                issues.append(
                    f"spreadsheet row {row_number}: the three topic preferences must be unique"
                )

        elif allocation_path == "self_proposed":
            for field in (
                "self_proposed_thesis_title",
                "self_proposed_thesis_description",
                "self_proposed_thesis_language",
            ):
                value = clean_text(source[field])
                normalized[field] = value
                if not value:
                    issues.append(f"spreadsheet row {row_number}: '{field}' is required")
            languages = parse_languages(source["self_proposed_thesis_language"])
            normalized["self_proposed_thesis_language"] = "; ".join(languages)

        else:
            for field in (
                "carry_over_thesis_topic",
                "carry_over_thesis_language",
                "daily_supervisor_email",
                "thesis_promotor_email",
            ):
                value = clean_text(source[field])
                normalized[field] = value
                if not value:
                    issues.append(f"spreadsheet row {row_number}: '{field}' is required")
            languages = parse_languages(source["carry_over_thesis_language"])
            normalized["carry_over_thesis_language"] = "; ".join(languages)
            normalized["daily_supervisor_email"] = normalize_email(
                source["daily_supervisor_email"]
            )
            normalized["thesis_promotor_email"] = normalize_email(
                source["thesis_promotor_email"]
            )
            normalized["submitted_daily_supervisor_email"] = clean_text(
                source["daily_supervisor_email"]
            )
            normalized["submitted_thesis_promotor_email"] = clean_text(
                source["thesis_promotor_email"]
            )
            normalized["carry_over_thesis_description"] = clean_text(
                source["carry_over_thesis_description"]
            )

        rows.append(normalized)

    normalized_table = pd.DataFrame(rows)
    if issues:
        raise InputValidationError(issues)

    duplicate_primary = normalized_table["email"].duplicated(keep=False)
    if duplicate_primary.any():
        emails = sorted(normalized_table.loc[duplicate_primary, "email"].unique())
        if duplicate_policy == "error":
            raise InputValidationError(
                "Student emails must be unique; duplicate value(s): "
                + ", ".join(emails)
            )
        keep = "first" if duplicate_policy == "keep-first" else "last"
        normalized_table = normalized_table.drop_duplicates("email", keep=keep)

    seen: dict[str, str] = {}
    member_issues: list[str] = []
    for _, row in normalized_table.iterrows():
        for member_email in (row["email"], row["partner_email"]):
            if not member_email:
                continue
            prior = seen.get(member_email)
            if prior and prior != row["thesis_group_id"]:
                member_issues.append(
                    f"student '{member_email}' appears in more than one thesis submission"
                )
            seen[member_email] = row["thesis_group_id"]
    if member_issues:
        raise InputValidationError(member_issues)
    return normalized_table.sort_values("_form_order").reset_index(drop=True)


def expand_group_assignments(assignments: pd.DataFrame) -> pd.DataFrame:
    """Expand group-level results to one auditable row per student."""

    rows: list[dict[str, object]] = []
    for _, group in assignments.iterrows():
        primary = group.to_dict()
        primary["group_member_role"] = "primary"
        rows.append(primary)
        if clean_text(group.get("partner_email")):
            partner = group.to_dict()
            partner["full_name"] = clean_text(group.get("partner_full_name"))
            partner["email"] = normalize_email(group.get("partner_email"))
            partner["student_number"] = clean_text(group.get("partner_student_number"))
            partner["group_member_role"] = "partner"
            rows.append(partner)
    return pd.DataFrame(rows).drop(columns=["_form_order"], errors="ignore")
