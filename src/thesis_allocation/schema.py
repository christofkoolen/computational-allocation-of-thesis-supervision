"""Canonical input schemas and legacy column aliases."""

from __future__ import annotations

from collections.abc import Iterable
from numbers import Integral, Real

import pandas as pd

from thesis_allocation.errors import InputValidationError


OWN_TOPIC_ID = "9999"

RESEARCHER_ALIASES = {
    "full_name": ("name", "researcher_name"),
    "email": ("e-mail", "e-mail address", "researcher_email"),
    "appointment": ("role", "position"),
    "supervision_languages": (
        "languages",
        "allowed_languages",
        "supervision_language",
    ),
    "profile_url": ("profile", "staff_profile_url"),
    "publications_url": ("publication_url", "lirias_url"),
    "profile_description": ("profile_text", "description"),
    "publication_list": ("publications", "publication_text"),
    "daily_supervisor_minimum_theses": (
        "daily_supervisor_min",
        "daily_minimum_theses",
    ),
    "daily_supervisor_maximum_theses": (
        "daily_supervisor_max",
        "daily_maximum_theses",
    ),
    "promotor_minimum_theses": ("promotor_min", "promoter_minimum_theses"),
    "promotor_maximum_theses": ("promotor_max", "promoter_maximum_theses"),
}

TOPIC_ALIASES = {
    "topic_id": ("id", "topic_code"),
    "topic_title": ("title", "proposed_thesis_topic", "assigned_topic"),
    "topic_description": (
        "description",
        "subject_field",
        "subject_fields",
        "topic_text",
    ),
    "submitter_email": (
        "researcher_email",
        "topic_submitter_email",
        "proposer_email",
    ),
    "capacity": ("topic_capacity", "places"),
}

PREFERENCE_ALIASES = {
    "full_name": ("name", "student_name"),
    "email": ("e-mail", "e-mail address", "student_email"),
    "preference_1": ("topic_1", "first_choice", "choice_1"),
    "preference_2": ("topic_2", "second_choice", "choice_2"),
    "preference_3": ("topic_3", "third_choice", "choice_3"),
    "own_topic_description": (
        "own_topic",
        "own_topic_text",
        "own_topic_short_description",
    ),
    "preference_1_languages": (
        "topic_1_language",
        "topic_1_languages",
        "first_choice_language",
    ),
    "preference_2_languages": (
        "topic_2_language",
        "topic_2_languages",
        "second_choice_language",
    ),
    "preference_3_languages": (
        "topic_3_language",
        "topic_3_languages",
        "third_choice_language",
    ),
}

ASSIGNMENT_ALIASES = {
    "full_name": ("name", "student_name"),
    "email": ("e-mail", "e-mail address", "student_email"),
    "assigned_topic_id": ("topic_id",),
    "assigned_topic": ("topic_title", "proposed_thesis_topic"),
    "daily_supervisor": ("daily_supervisor_name",),
    "daily_supervisor_email": (),
    "promotor": ("thesis_promotor", "promoter"),
    "promotor_email": ("thesis_promotor_email", "promoter_email"),
}

CAPACITY_COLUMNS = (
    "daily_supervisor_minimum_theses",
    "daily_supervisor_maximum_theses",
    "promotor_minimum_theses",
    "promotor_maximum_theses",
)


def clean_text(value: object) -> str:
    """Convert a scalar to stripped text while treating missing values as blank."""

    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    return str(value).strip()


def normalize_email(value: object) -> str:
    """Normalize an email for matching and identifiers."""

    return clean_text(value).casefold()


def normalize_topic_id(value: object) -> str:
    """Normalize a topic identifier without changing meaningful string formatting."""

    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    if isinstance(value, Integral) and not isinstance(value, bool):
        return str(int(value))
    if isinstance(value, Real) and not isinstance(value, bool):
        numeric = float(value)
        if numeric.is_integer():
            return str(int(numeric))
    return str(value).strip()


def normalized_key(value: object) -> str:
    """Normalize free text for exact matching."""

    return " ".join(clean_text(value).casefold().split())


def _column_lookup(columns: Iterable[object]) -> dict[str, object]:
    return {clean_text(column).casefold(): column for column in columns}


def _copy_alias(
    frame: pd.DataFrame,
    target: str,
    aliases: Iterable[str],
    *,
    required: bool = False,
    default: object = "",
) -> bool:
    lookup = _column_lookup(frame.columns)
    for candidate in (target, *aliases):
        source = lookup.get(candidate.casefold())
        if source is not None:
            if source != target:
                frame[target] = frame[source]
            return True
    if required:
        return False
    frame[target] = default
    return True


def _require_nonempty(frame: pd.DataFrame, columns: Iterable[str]) -> list[str]:
    issues: list[str] = []
    for column in columns:
        blank_rows = [
            str(index + 2)
            for index, value in enumerate(frame[column])
            if not clean_text(value)
        ]
        if blank_rows:
            preview = ", ".join(blank_rows[:8])
            suffix = " ..." if len(blank_rows) > 8 else ""
            issues.append(f"'{column}' is blank on spreadsheet row(s) {preview}{suffix}")
    return issues


def _validate_unique(frame: pd.DataFrame, column: str, label: str) -> list[str]:
    values = frame[column].map(normalized_key)
    duplicates = sorted(
        {
            clean_text(frame.loc[index, column])
            for index in frame.index[values.duplicated(keep=False)]
        }
    )
    if not duplicates:
        return []
    return [f"{label} must be unique; duplicate value(s): {', '.join(duplicates)}"]


def _numeric_capacity(frame: pd.DataFrame, column: str) -> list[str]:
    issues: list[str] = []
    converted = pd.to_numeric(frame[column], errors="coerce")
    invalid = frame[column].map(clean_text).ne("") & converted.isna()
    if invalid.any():
        rows = ", ".join(str(index + 2) for index in frame.index[invalid][:8])
        issues.append(f"'{column}' must contain whole numbers; invalid row(s): {rows}")
    converted = converted.fillna(0)
    fractional = converted.mod(1).ne(0)
    negative = converted.lt(0)
    if fractional.any() or negative.any():
        bad = fractional | negative
        rows = ", ".join(str(index + 2) for index in frame.index[bad][:8])
        issues.append(
            f"'{column}' must contain non-negative whole numbers; invalid row(s): {rows}"
        )
    frame[column] = converted.astype(int)
    return issues


def normalize_researchers(
    frame: pd.DataFrame,
    *,
    require_capacities: bool = False,
) -> pd.DataFrame:
    """Return researcher data using canonical names and validated identifiers."""

    result = frame.copy()
    issues: list[str] = []
    for target, aliases in RESEARCHER_ALIASES.items():
        required = target in {"full_name", "email"} or (
            require_capacities and target in CAPACITY_COLUMNS
        )
        if not _copy_alias(result, target, aliases, required=required):
            issues.append(
                f"researchers is missing '{target}' "
                f"(accepted aliases: {', '.join(aliases) or 'none'})"
            )

    if issues:
        raise InputValidationError(issues)

    result["full_name"] = result["full_name"].map(clean_text)
    result["email"] = result["email"].map(normalize_email)
    result["appointment"] = result["appointment"].map(clean_text)
    for column in (
        "supervision_languages",
        "profile_url",
        "publications_url",
        "profile_description",
        "publication_list",
    ):
        result[column] = result[column].map(clean_text)

    issues.extend(_require_nonempty(result, ("full_name", "email")))
    issues.extend(_validate_unique(result, "email", "Researcher emails"))
    for column in CAPACITY_COLUMNS:
        issues.extend(_numeric_capacity(result, column))

    for prefix in ("daily_supervisor", "promotor"):
        minimum = f"{prefix}_minimum_theses"
        maximum = f"{prefix}_maximum_theses"
        invalid = result[minimum].gt(result[maximum])
        if invalid.any():
            rows = ", ".join(str(index + 2) for index in result.index[invalid][:8])
            issues.append(
                f"'{minimum}' cannot exceed '{maximum}'; invalid row(s): {rows}"
            )

    if issues:
        raise InputValidationError(issues)
    return result.reset_index(drop=True)


def normalize_topics(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a one-row-per-topic canonical table with mandatory stable IDs."""

    result = frame.copy()
    issues: list[str] = []
    for target, aliases in TOPIC_ALIASES.items():
        if not _copy_alias(
            result,
            target,
            aliases,
            required=target in {"topic_id", "topic_title"},
            default=1 if target == "capacity" else "",
        ):
            issues.append(
                f"topics is missing '{target}' "
                f"(accepted aliases: {', '.join(aliases) or 'none'})"
            )
    if issues:
        raise InputValidationError(issues)

    result["topic_id"] = result["topic_id"].map(normalize_topic_id)
    result["topic_title"] = result["topic_title"].map(clean_text)
    result["topic_description"] = result["topic_description"].map(clean_text)
    result["submitter_email"] = result["submitter_email"].map(normalize_email)
    issues.extend(_require_nonempty(result, ("topic_id", "topic_title")))
    issues.extend(_validate_unique(result, "topic_id", "Topic IDs"))
    issues.extend(_validate_unique(result, "topic_title", "Topic titles"))

    reserved = result["topic_id"].eq(OWN_TOPIC_ID)
    if reserved.any():
        rows = ", ".join(str(index + 2) for index in result.index[reserved][:8])
        issues.append(
            f"topic ID {OWN_TOPIC_ID} is reserved for a student's own topic and "
            f"must not appear in the topics file; invalid row(s): {rows}"
        )

    issues.extend(_numeric_capacity(result, "capacity"))
    invalid_capacity = result["capacity"].lt(1)
    if invalid_capacity.any():
        rows = ", ".join(
            str(index + 2) for index in result.index[invalid_capacity][:8]
        )
        issues.append(f"'capacity' must be at least 1; invalid row(s): {rows}")

    result["topic_text"] = (
        result["topic_title"] + " " + result["topic_description"]
    ).str.strip()
    if issues:
        raise InputValidationError(issues)
    return result.reset_index(drop=True)


def normalize_preferences(
    frame: pd.DataFrame,
    *,
    duplicate_policy: str = "keep-last",
) -> pd.DataFrame:
    """Return canonical top-three topic-ID preferences and validate own topics."""

    if duplicate_policy not in {"error", "keep-first", "keep-last"}:
        raise ValueError("duplicate_policy must be error, keep-first, or keep-last")

    result = frame.copy()
    issues: list[str] = []
    for target, aliases in PREFERENCE_ALIASES.items():
        required = target in {
            "full_name",
            "email",
            "preference_1",
            "preference_2",
            "preference_3",
        }
        if not _copy_alias(result, target, aliases, required=required):
            issues.append(
                f"student preferences is missing '{target}' "
                f"(accepted aliases: {', '.join(aliases) or 'none'})"
            )
    if issues:
        raise InputValidationError(issues)

    result["full_name"] = result["full_name"].map(clean_text)
    result["email"] = result["email"].map(normalize_email)
    result["own_topic_description"] = result["own_topic_description"].map(clean_text)
    for rank in (1, 2, 3):
        result[f"preference_{rank}"] = result[f"preference_{rank}"].map(
            normalize_topic_id
        )
        result[f"preference_{rank}_languages"] = result[
            f"preference_{rank}_languages"
        ].map(clean_text)

    issues.extend(
        _require_nonempty(
            result,
            ("full_name", "email", "preference_1", "preference_2", "preference_3"),
        )
    )

    for _, row in result.iterrows():
        preferences = [row[f"preference_{rank}"] for rank in (1, 2, 3)]
        if len(set(preferences)) != len(preferences):
            issues.append(
                f"student '{row['email']}' must provide three different topic IDs"
            )
        if OWN_TOPIC_ID in preferences and not row["own_topic_description"]:
            issues.append(
                f"student '{row['email']}' selected topic ID {OWN_TOPIC_ID} "
                "but 'own_topic_description' is blank"
            )

    duplicate_mask = result["email"].duplicated(keep=False)
    if duplicate_mask.any() and duplicate_policy == "error":
        emails = sorted(result.loc[duplicate_mask, "email"].unique())
        issues.append(
            f"Student emails must be unique; duplicate value(s): {', '.join(emails)}"
        )
    if issues:
        raise InputValidationError(issues)

    if duplicate_mask.any():
        keep = "first" if duplicate_policy == "keep-first" else "last"
        result = result.drop_duplicates("email", keep=keep)
    return result.reset_index(drop=True)


def normalize_assignments(frame: pd.DataFrame) -> pd.DataFrame:
    """Return an assignment table with canonical student, topic, and role columns."""

    result = frame.copy()
    issues: list[str] = []
    for target, aliases in ASSIGNMENT_ALIASES.items():
        required = target in {"full_name", "email", "assigned_topic"}
        if not _copy_alias(result, target, aliases, required=required):
            issues.append(
                f"assignments is missing '{target}' "
                f"(accepted aliases: {', '.join(aliases) or 'none'})"
            )
    if issues:
        raise InputValidationError(issues)

    if "own_topic_description" not in result.columns:
        result["own_topic_description"] = ""

    result["full_name"] = result["full_name"].map(clean_text)
    result["email"] = result["email"].map(normalize_email)
    result["assigned_topic_id"] = result["assigned_topic_id"].map(normalize_topic_id)
    result["assigned_topic"] = result["assigned_topic"].map(clean_text)
    result["own_topic_description"] = result["own_topic_description"].map(clean_text)
    for column in (
        "daily_supervisor",
        "daily_supervisor_email",
        "promotor",
        "promotor_email",
    ):
        normalizer = normalize_email if column.endswith("_email") else clean_text
        result[column] = result[column].map(normalizer)

    issues.extend(_require_nonempty(result, ("full_name", "email")))
    issues.extend(_validate_unique(result, "email", "Student emails"))
    own_topic_missing = result["assigned_topic_id"].eq(OWN_TOPIC_ID) & result[
        "own_topic_description"
    ].eq("")
    if own_topic_missing.any():
        students = ", ".join(result.loc[own_topic_missing, "email"].tolist())
        issues.append(
            f"Assigned own topics ({OWN_TOPIC_ID}) require 'own_topic_description' "
            f"for student(s): {students}"
        )
    if issues:
        raise InputValidationError(issues)
    return result.reset_index(drop=True)
