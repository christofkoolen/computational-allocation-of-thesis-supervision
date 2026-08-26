"""Capacity-constrained semantic matching of supervisors to assigned topics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
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
    normalize_assignments,
    normalize_email,
    normalize_researchers,
    normalize_topic_id,
    normalize_topics,
    normalized_key,
)
from thesis_allocation.similarity import SimilarityBackend
from thesis_allocation.topics import TopicResolver


SIMILARITY_COST_SCALE = 1_000
MINIMUM_PRIORITY_PENALTY = 1_000_000


@dataclass(frozen=True)
class RoleSpec:
    """Column contract for one supervision role."""

    key: str
    label: str
    name_column: str
    email_column: str
    minimum_column: str
    maximum_column: str
    score_column: str
    source_column: str


ROLE_SPECS = {
    "daily_supervisor": RoleSpec(
        key="daily_supervisor",
        label="Daily supervisor",
        name_column="daily_supervisor",
        email_column="daily_supervisor_email",
        minimum_column="daily_supervisor_minimum_theses",
        maximum_column="daily_supervisor_maximum_theses",
        score_column="daily_supervisor_match_score",
        source_column="daily_supervisor_assignment_source",
    ),
    "promotor": RoleSpec(
        key="promotor",
        label="Promotor",
        name_column="promotor",
        email_column="promotor_email",
        minimum_column="promotor_minimum_theses",
        maximum_column="promotor_maximum_theses",
        score_column="promotor_match_score",
        source_column="promotor_assignment_source",
    ),
}


@dataclass(frozen=True)
class MatchResult:
    """Final assignments, workload summary, and non-fatal policy warnings."""

    assignments: pd.DataFrame
    summary: pd.DataFrame
    warnings: tuple[str, ...] = ()


def _researcher_maps(
    researchers: pd.DataFrame,
) -> tuple[dict[str, pd.Series], dict[str, list[pd.Series]]]:
    by_email = {row["email"]: row for _, row in researchers.iterrows()}
    by_name: dict[str, list[pd.Series]] = {}
    for _, row in researchers.iterrows():
        by_name.setdefault(normalized_key(row["full_name"]), []).append(row)
    return by_email, by_name


def _supports_assignment_language(
    assigned_language: object,
    supervision_languages: object,
) -> bool:
    """Return whether a researcher can supervise in the assignment language."""

    compatible, _ = first_compatible_language(
        assigned_language,
        supervision_languages,
    )
    return compatible


def _canonicalize_preassignments(
    assignments: pd.DataFrame,
    researchers: pd.DataFrame,
    spec: RoleSpec,
) -> pd.DataFrame:
    """Resolve existing assignments by email, or by an unambiguous name fallback."""

    result = assignments.copy()
    by_email, by_name = _researcher_maps(researchers)
    issues: list[str] = []

    if spec.score_column not in result.columns:
        result[spec.score_column] = np.nan
    if spec.source_column not in result.columns:
        result[spec.source_column] = ""

    for index, row in result.iterrows():
        supplied_email = normalize_email(row.get(spec.email_column))
        supplied_name = clean_text(row.get(spec.name_column))
        if not supplied_email and not supplied_name:
            result.at[index, spec.email_column] = ""
            result.at[index, spec.name_column] = ""
            continue

        candidate: pd.Series | None = None
        if supplied_email:
            candidate = by_email.get(supplied_email)
            if candidate is None:
                issues.append(
                    f"student '{row['email']}' has unknown {spec.label.casefold()} "
                    f"email '{supplied_email}'"
                )
                continue
        else:
            matches = by_name.get(normalized_key(supplied_name), [])
            if len(matches) != 1:
                qualifier = "unknown" if not matches else "ambiguous"
                issues.append(
                    f"student '{row['email']}' has {qualifier} "
                    f"{spec.label.casefold()} name '{supplied_name}'; provide the email"
                )
                continue
            candidate = matches[0]

        if supplied_name and normalized_key(supplied_name) != normalized_key(
            candidate["full_name"]
        ):
            issues.append(
                f"student '{row['email']}' has conflicting {spec.label.casefold()} "
                f"name and email"
            )
            continue

        assigned_language = clean_text(row.get("assigned_language"))
        if not _supports_assignment_language(
            assigned_language,
            candidate["supervision_languages"],
        ):
            issues.append(
                f"student '{row['email']}' has preassigned {spec.label.casefold()} "
                f"'{candidate['email']}' who does not supervise in "
                f"'{assigned_language}'"
            )
            continue

        result.at[index, spec.email_column] = candidate["email"]
        result.at[index, spec.name_column] = candidate["full_name"]
        if not clean_text(result.at[index, spec.source_column]):
            result.at[index, spec.source_column] = "preassigned"

    if issues:
        raise InputValidationError(issues)
    return result


def _attach_topic_context(
    assignments: pd.DataFrame,
    topics: pd.DataFrame,
) -> pd.DataFrame:
    result = assignments.copy()
    resolver = TopicResolver(topics)
    issues: list[str] = []

    result["_topic_text"] = ""
    result["_submitter_email"] = ""
    for index, row in result.iterrows():
        reference = normalize_topic_id(row.get("assigned_topic_id"))
        if not reference:
            issues.append(
                f"student '{row['email']}': assigned_topic_id is blank; "
                "topic titles are no longer used as identifiers"
            )
            continue

        assignment_source = clean_text(row.get("topic_assignment_source")).casefold()
        if assignment_source == "carry_over":
            title = clean_text(row.get("assigned_topic"))
            description = clean_text(row.get("assigned_topic_description"))
            if not title:
                issues.append(
                    f"student '{row['email']}': carried assignment requires "
                    "assigned_topic"
                )
                continue
            result.at[index, "_topic_text"] = " ".join(
                part for part in (title, description) if part
            )
            result.at[index, "_submitter_email"] = ""
            continue

        if reference == OWN_TOPIC_ID:
            description = clean_text(row.get("own_topic_description"))
            if not description:
                issues.append(
                    f"student '{row['email']}': topic ID {OWN_TOPIC_ID} requires "
                    "own_topic_description"
                )
                continue
            result.at[index, "assigned_topic_id"] = OWN_TOPIC_ID
            result.at[index, "assigned_topic"] = "Own topic"
            result.at[index, "assigned_topic_description"] = description
            result.at[index, "_topic_text"] = description
            result.at[index, "_submitter_email"] = ""
            continue

        try:
            topic_index = resolver.resolve(reference)
        except InputValidationError as exc:
            issues.extend(
                f"student '{row['email']}': {issue}" for issue in exc.issues
            )
            continue
        topic = topics.loc[topic_index]
        result.at[index, "assigned_topic_id"] = topic["topic_id"]
        result.at[index, "assigned_topic"] = topic["topic_title"]
        result.at[index, "assigned_topic_description"] = topic["topic_description"]
        result.at[index, "_topic_text"] = topic["topic_text"]
        result.at[index, "_submitter_email"] = topic["submitter_email"]

    if issues:
        raise InputValidationError(issues)
    return result


def _other_role(spec: RoleSpec) -> RoleSpec:
    return (
        ROLE_SPECS["promotor"]
        if spec.key == "daily_supervisor"
        else ROLE_SPECS["daily_supervisor"]
    )


def _candidate_text(researchers: pd.DataFrame) -> pd.Series:
    return (
        researchers["profile_description"].fillna("").map(clean_text)
        + " "
        + researchers["publication_list"].fillna("").map(clean_text)
    ).str.strip()


def _assign_role(
    assignments: pd.DataFrame,
    researchers: pd.DataFrame,
    spec: RoleSpec,
    backend: SimilarityBackend,
    *,
    allow_partial: bool,
    enforce_distinct_roles: bool,
    excluded_researcher_emails: set[str],
    load_balance_cost: int,
    target_student_emails: set[str] | None,
) -> tuple[pd.DataFrame, list[str]]:
    result = assignments.copy()
    warnings: list[str] = []

    candidates = researchers[
        researchers[spec.maximum_column].gt(0)
        & ~researchers["email"].isin(excluded_researcher_emails)
    ].copy()
    candidates = candidates.sort_values("email").reset_index(drop=True)
    candidates["_profile_text"] = _candidate_text(candidates)

    target_indices = [
        index
        for index, value in result[spec.email_column].items()
        if not normalize_email(value)
        and clean_text(result.at[index, "_topic_text"])
        and (
            target_student_emails is None
            or result.at[index, "email"] in target_student_emails
        )
    ]
    if not target_indices:
        return result, warnings
    if candidates.empty:
        raise InfeasibleAssignmentError(
            f"No eligible {spec.label.casefold()} candidates have remaining policy scope"
        )
    if candidates["_profile_text"].eq("").all():
        warnings.append(
            f"All eligible {spec.label.casefold()} profiles are blank; "
            "assignments will be driven by capacity and submitter priority"
        )

    current_load = (
        result.loc[
            result[spec.email_column].map(normalize_email).ne(""),
            spec.email_column,
        ]
        .map(normalize_email)
        .value_counts()
        .to_dict()
    )
    all_researchers = researchers.set_index("email")
    issues: list[str] = []
    for email, load in current_load.items():
        if email not in all_researchers.index:
            continue
        maximum = int(all_researchers.at[email, spec.maximum_column])
        if load > maximum:
            issues.append(
                f"{spec.label} '{email}' has {load} preassignments but maximum "
                f"capacity is {maximum}"
            )
    if issues:
        raise InputValidationError(issues)

    queries = [clean_text(result.at[index, "_topic_text"]) for index in target_indices]
    candidate_texts = candidates["_profile_text"].tolist()
    similarity = np.asarray(backend.score(queries, candidate_texts), dtype=float)
    expected_shape = (len(target_indices), len(candidates))
    if similarity.shape != expected_shape:
        raise ValueError(
            f"Similarity backend returned {similarity.shape}; expected {expected_shape}"
        )

    maximum_slot_index = max(
        max(0, int(candidate[spec.maximum_column]) - 1)
        for _, candidate in candidates.iterrows()
    )
    maximum_secondary_path_cost = (
        MINIMUM_PRIORITY_PENALTY
        + (2 * SIMILARITY_COST_SCALE)
        + (load_balance_cost * maximum_slot_index)
    )
    non_submitter_penalty = (
        len(target_indices) * maximum_secondary_path_cost
    ) + 1

    source = 0
    student_start = 1
    candidate_start = student_start + len(target_indices)
    sink = candidate_start + len(candidates)
    network = MinCostFlow(sink + 1)

    for offset in range(len(target_indices)):
        network.add_edge(source, student_start + offset, 1, 0)

    for candidate_offset, candidate in candidates.iterrows():
        email = candidate["email"]
        current = int(current_load.get(email, 0))
        minimum = int(candidate[spec.minimum_column])
        maximum = int(candidate[spec.maximum_column])
        remaining = max(0, maximum - current)
        remaining_minimum = max(0, minimum - current)
        for slot in range(remaining):
            minimum_penalty = (
                0 if slot < remaining_minimum else MINIMUM_PRIORITY_PENALTY
            )
            balancing_penalty = load_balance_cost * (current + slot)
            network.add_edge(
                candidate_start + candidate_offset,
                sink,
                1,
                minimum_penalty + balancing_penalty,
            )

    other = _other_role(spec)
    for student_offset, assignment_index in enumerate(target_indices):
        other_email = normalize_email(result.at[assignment_index, other.email_column])
        submitter_email = normalize_email(
            result.at[assignment_index, "_submitter_email"]
        )
        assigned_language = (
            clean_text(result.at[assignment_index, "assigned_language"])
            if "assigned_language" in result.columns
            else ""
        )
        for candidate_offset, candidate in candidates.iterrows():
            candidate_email = candidate["email"]
            if (
                enforce_distinct_roles
                and other_email
                and candidate_email == other_email
            ):
                continue
            if not _supports_assignment_language(
                assigned_language,
                candidate["supervision_languages"],
            ):
                continue

            raw_similarity = float(similarity[student_offset, candidate_offset])
            if not np.isfinite(raw_similarity):
                raw_similarity = 0.0
            clipped_similarity = min(1.0, max(-1.0, raw_similarity))
            semantic_cost = int(
                round((1.0 - clipped_similarity) * SIMILARITY_COST_SCALE)
            )
            is_submitter = bool(
                submitter_email and candidate_email == submitter_email
            )
            priority_cost = 0 if is_submitter else non_submitter_penalty
            network.add_edge(
                student_start + student_offset,
                candidate_start + candidate_offset,
                1,
                priority_cost + semantic_cost,
                data={
                    "assignment_index": assignment_index,
                    "candidate_offset": candidate_offset,
                    "similarity": raw_similarity,
                    "is_submitter": is_submitter,
                },
            )

    flow, _ = network.solve(source, sink, len(target_indices))
    selected = [edge.data for edge in network.used_data_edges()]
    selected_indices = {item["assignment_index"] for item in selected}
    unassigned_indices = sorted(set(target_indices) - selected_indices)
    if unassigned_indices and not allow_partial:
        students = ", ".join(result.at[index, "email"] for index in unassigned_indices)
        available_capacity = sum(
            max(
                0,
                int(row[spec.maximum_column])
                - int(current_load.get(row["email"], 0)),
            )
            for _, row in candidates.iterrows()
        )
        raise InfeasibleAssignmentError(
            f"A complete {spec.label.casefold()} assignment is impossible. "
            f"Assigned {flow} of {len(target_indices)} open students with "
            f"{available_capacity} available slots before language filtering. "
            f"Unassigned: {students}"
        )

    for item in selected:
        assignment_index = item["assignment_index"]
        candidate = candidates.iloc[item["candidate_offset"]]
        result.at[assignment_index, spec.name_column] = candidate["full_name"]
        result.at[assignment_index, spec.email_column] = candidate["email"]
        result.at[assignment_index, spec.score_column] = round(
            float(item["similarity"]),
            6,
        )
        result.at[assignment_index, spec.source_column] = (
            "topic_submitter" if item["is_submitter"] else "semantic"
        )

    if unassigned_indices:
        warnings.append(
            f"Partial {spec.label.casefold()} assignment: "
            f"{len(unassigned_indices)} student(s) remain open after capacity, "
            "role, and language constraints"
        )

    final_load = (
        result.loc[
            result[spec.email_column].map(normalize_email).ne(""),
            spec.email_column,
        ]
        .map(normalize_email)
        .value_counts()
        .to_dict()
    )
    unmet = []
    for _, candidate in candidates.iterrows():
        required = int(candidate[spec.minimum_column])
        assigned = int(final_load.get(candidate["email"], 0))
        if assigned < required:
            unmet.append(f"{candidate['full_name']} ({assigned}/{required})")
    if unmet:
        warnings.append(
            f"{spec.label} minimum targets remain unmet: {', '.join(unmet)}"
        )
    return result, warnings


def _validate_distinct_preassignments(assignments: pd.DataFrame) -> None:
    conflicts = assignments[
        assignments["daily_supervisor_email"].map(normalize_email).ne("")
        & assignments["daily_supervisor_email"].map(normalize_email).eq(
            assignments["promotor_email"].map(normalize_email)
        )
    ]
    if conflicts.empty:
        return
    students = ", ".join(conflicts["email"].tolist())
    raise InputValidationError(
        "Daily supervisor and promotor must be different people for student(s): "
        f"{students}"
    )


def build_workload_summary(
    assignments: pd.DataFrame,
    researchers: pd.DataFrame,
) -> pd.DataFrame:
    """Build one auditable capacity and workload row per researcher."""

    summary = researchers[
        [
            "full_name",
            "email",
            "appointment",
            "supervision_languages",
            "daily_supervisor_minimum_theses",
            "daily_supervisor_maximum_theses",
            "promotor_minimum_theses",
            "promotor_maximum_theses",
        ]
    ].copy()
    for role_key, spec in ROLE_SPECS.items():
        del role_key
        counts = (
            assignments[spec.email_column]
            .map(normalize_email)
            .loc[lambda values: values.ne("")]
            .value_counts()
        )
        count_column = f"assigned_{spec.key}_theses"
        summary[count_column] = summary["email"].map(counts).fillna(0).astype(int)
        summary[f"{spec.key}_below_minimum"] = (
            summary[count_column] < summary[spec.minimum_column]
        )
        summary[f"{spec.key}_over_maximum"] = (
            summary[count_column] > summary[spec.maximum_column]
        )
    return summary.sort_values("full_name").reset_index(drop=True)


def match_supervisors(
    assignments: pd.DataFrame,
    researchers: pd.DataFrame,
    topics: pd.DataFrame,
    backend: SimilarityBackend,
    *,
    roles: tuple[str, ...] = ("daily_supervisor", "promotor"),
    allow_partial: bool = False,
    enforce_distinct_roles: bool = True,
    excluded_researcher_emails: set[str] | None = None,
    target_student_emails: set[str] | None = None,
    load_balance_cost: int = 25,
) -> MatchResult:
    """Assign requested supervision roles while preserving existing assignments."""

    unknown_roles = sorted(set(roles) - set(ROLE_SPECS))
    if unknown_roles:
        raise InputValidationError(f"Unknown role(s): {', '.join(unknown_roles)}")
    if load_balance_cost < 0:
        raise ValueError("Matching cost parameters must be non-negative")

    researcher_table = normalize_researchers(
        researchers,
        require_capacities=True,
    )
    topic_table = normalize_topics(topics)
    result = normalize_assignments(assignments)
    missing_topics = result["assigned_topic_id"].map(normalize_topic_id).eq("")
    if missing_topics.any() and not allow_partial:
        students = ", ".join(result.loc[missing_topics, "email"].tolist())
        raise InputValidationError(
            f"Assigned topic ID is blank for student(s): {students}"
        )
    result = _attach_topic_context(result, topic_table)
    for spec in ROLE_SPECS.values():
        result = _canonicalize_preassignments(result, researcher_table, spec)

    if enforce_distinct_roles:
        _validate_distinct_preassignments(result)

    excluded = {
        normalize_email(email)
        for email in (excluded_researcher_emails or set())
        if normalize_email(email)
    }
    targets = (
        {
            normalize_email(email)
            for email in target_student_emails
            if normalize_email(email)
        }
        if target_student_emails is not None
        else None
    )
    warnings: list[str] = []
    if missing_topics.any():
        warnings.append(
            f"{int(missing_topics.sum())} student(s) without a topic were left "
            "without new supervisor assignments"
        )
    for role in roles:
        result, role_warnings = _assign_role(
            result,
            researcher_table,
            ROLE_SPECS[role],
            backend,
            allow_partial=allow_partial,
            enforce_distinct_roles=enforce_distinct_roles,
            excluded_researcher_emails=excluded,
            load_balance_cost=load_balance_cost,
            target_student_emails=targets,
        )
        warnings.extend(role_warnings)

    summary = build_workload_summary(result, researcher_table)
    result = result.drop(columns=["_topic_text", "_submitter_email"])
    return MatchResult(
        assignments=result,
        summary=summary,
        warnings=tuple(dict.fromkeys(warnings)),
    )
