"""Joint topic, language, and supervision allocation for Forms submissions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from thesis_allocation.errors import InfeasibleAssignmentError, InputValidationError
from thesis_allocation.forms import expand_group_assignments, normalize_forms_submissions
from thesis_allocation.languages import first_compatible_language, parse_languages
from thesis_allocation.matching import ROLE_SPECS, build_workload_summary
from thesis_allocation.schema import (
    clean_text,
    normalize_email,
    normalize_researchers,
    normalize_topics,
)
from thesis_allocation.similarity import SimilarityBackend
from thesis_allocation.topics import TopicResolver


@dataclass(frozen=True)
class _Option:
    group: int
    topic_id: str
    title: str
    description: str
    submitter_email: str
    capacity_key: str | None
    rank: int | None
    language: str
    language_rank: int
    source: str

    @property
    def text(self) -> str:
        return " ".join(part for part in (self.title, self.description) if part)


@dataclass(frozen=True)
class GroupedAllocationResult:
    """Expanded student results plus group-aware diagnostics."""

    assignments: pd.DataFrame
    group_assignments: pd.DataFrame
    summary: pd.DataFrame
    preference_cost: int
    assigned_students: int
    assigned_theses: int
    carry_over_theses: int
    self_proposed_theses: int
    dual_theses: int
    manual_review_theses: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class _EmailResolution:
    submitted: str
    resolved: str
    method: str
    score: float


MANUAL_REVIEW_NEEDED = "MANUAL REVIEW NEEDED"

ROLE_REVIEW_LABELS = {
    "daily_supervisor": "DAILY SUPERVISOR",
    "thesis_promotor": "THESIS PROMOTOR",
}

ROLE_AUDIT_FIELDS = {
    "daily_supervisor": (
        "resolved_daily_supervisor_email",
        "daily_supervisor",
        "DAILY SUPERVISOR",
    ),
    "promotor": (
        "resolved_thesis_promotor_email",
        "thesis_promotor",
        "THESIS PROMOTOR",
    ),
}


def _append_review_reason(existing: object, reason: str) -> str:
    current = clean_text(existing)
    return f"{current} | {reason}" if current else reason


def _damerau_levenshtein(left: str, right: str) -> int:
    """Return optimal-string-alignment edit distance, including transposition."""

    rows = len(left) + 1
    columns = len(right) + 1
    distance = [[0] * columns for _ in range(rows)]
    for row in range(rows):
        distance[row][0] = row
    for column in range(columns):
        distance[0][column] = column
    for row in range(1, rows):
        for column in range(1, columns):
            substitution = 0 if left[row - 1] == right[column - 1] else 1
            distance[row][column] = min(
                distance[row - 1][column] + 1,
                distance[row][column - 1] + 1,
                distance[row - 1][column - 1] + substitution,
            )
            if (
                row > 1
                and column > 1
                and left[row - 1] == right[column - 2]
                and left[row - 2] == right[column - 1]
            ):
                distance[row][column] = min(
                    distance[row][column],
                    distance[row - 2][column - 2] + 1,
                )
    return distance[-1][-1]


def _email_similarity(left: str, right: str) -> tuple[int, float]:
    distance = _damerau_levenshtein(left, right)
    length = max(len(left), len(right), 1)
    return distance, 1.0 - (distance / length)


def _resolve_email(
    submitted: object,
    researcher_emails: list[str],
) -> tuple[_EmailResolution | None, list[tuple[str, int, float]]]:
    normalized = normalize_email(submitted)
    if normalized in researcher_emails:
        return _EmailResolution(clean_text(submitted), normalized, "exact", 1.0), []

    candidates = sorted(
        (
            (candidate, *_email_similarity(normalized, candidate))
            for candidate in researcher_emails
        ),
        key=lambda item: (item[1], -item[2], item[0]),
    )
    if not candidates:
        return None, []
    best_email, best_distance, best_score = candidates[0]
    runner_up_score = candidates[1][2] if len(candidates) > 1 else -1.0
    uniquely_close = (
        best_distance <= 1
        and best_score >= 0.94
        and best_score - runner_up_score >= 0.03
    )
    if uniquely_close:
        return (
            _EmailResolution(
                clean_text(submitted),
                best_email,
                "fuzzy_match",
                round(best_score, 6),
            ),
            candidates[:3],
        )
    return None, candidates[:3]


def _resolve_carry_over_emails(
    groups: pd.DataFrame,
    researchers: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    result = groups.copy()
    researcher_emails = researchers["email"].tolist()
    warnings: list[str] = []
    result["carry_over_review_status"] = ""
    result["carry_over_review_reason"] = ""
    fields = {
        "daily_supervisor": (
            "daily_supervisor_email",
            "submitted_daily_supervisor_email",
            "resolved_daily_supervisor_email",
        ),
        "thesis_promotor": (
            "thesis_promotor_email",
            "submitted_thesis_promotor_email",
            "resolved_thesis_promotor_email",
        ),
    }
    for label, (_, _, audit_column) in fields.items():
        result[audit_column] = ""
        result[f"{label}_email_resolution"] = ""
        result[f"{label}_email_match_score"] = pd.NA
        result[f"{label}_review_status"] = ""
        result[f"{label}_review_reason"] = ""
    for group_index, group in result.iterrows():
        if group["allocation_path"] != "carry_over":
            continue
        for label, (resolved_column, submitted_column, audit_column) in fields.items():
            submitted = group[submitted_column]
            resolution, candidates = _resolve_email(submitted, researcher_emails)
            method_column = f"{label}_email_resolution"
            score_column = f"{label}_email_match_score"
            if resolution is None:
                suggestions = ", ".join(candidate[0] for candidate in candidates)
                suffix = (
                    f" Closest candidate(s): {suggestions}."
                    if suggestions
                    else " The researchers file contains no candidate emails."
                )
                reason = (
                    f"Submitted {label.replace('_', ' ')} email "
                    f"'{clean_text(submitted)}' could not be matched confidently in "
                    "researchers.xlsx. The researcher may have left or the address may "
                    f"be incorrect.{suffix} A replacement was assigned where feasible."
                )
                review_status = (
                    f"{MANUAL_REVIEW_NEEDED} - UNKNOWN {ROLE_REVIEW_LABELS[label]}"
                )
                result.at[group_index, resolved_column] = ""
                result.at[group_index, audit_column] = ""
                result.at[group_index, method_column] = "manual_review"
                result.at[group_index, score_column] = (
                    round(candidates[0][2], 6) if candidates else 0.0
                )
                result.at[group_index, f"{label}_review_status"] = review_status
                result.at[group_index, f"{label}_review_reason"] = reason
                result.at[group_index, "carry_over_review_status"] = (
                    _append_review_reason(
                        result.at[group_index, "carry_over_review_status"],
                        review_status,
                    )
                )
                result.at[group_index, "carry_over_review_reason"] = (
                    _append_review_reason(
                        result.at[group_index, "carry_over_review_reason"], reason
                    )
                )
                warnings.append(
                    f"Carry-over thesis '{group['thesis_group_id']}': "
                    f"{review_status}. {reason}"
                )
                continue
            result.at[group_index, resolved_column] = resolution.resolved
            result.at[group_index, audit_column] = resolution.resolved
            result.at[group_index, method_column] = resolution.method
            result.at[group_index, score_column] = resolution.score
            if resolution.method == "fuzzy_match":
                warnings.append(
                    f"Carry-over thesis '{group['thesis_group_id']}': corrected "
                    f"submitted {label.replace('_', ' ')} email "
                    f"'{resolution.submitted}' to '{resolution.resolved}' "
                    f"(match score {resolution.score:.3f})"
                )
    return result, warnings


def _candidate_text(researchers: pd.DataFrame) -> pd.Series:
    return (
        researchers["profile_description"].fillna("").map(clean_text)
        + " "
        + researchers["publication_list"].fillna("").map(clean_text)
    ).str.strip()


def _build_options(groups: pd.DataFrame, topics: pd.DataFrame) -> list[_Option]:
    resolver = TopicResolver(topics)
    options: list[_Option] = []
    issues: list[str] = []
    for group_index, group in groups.iterrows():
        path = group["allocation_path"]
        if path == "ranked":
            for rank in (1, 2, 3):
                topic_id = group[f"topic_preference_{rank}"]
                try:
                    topic = topics.loc[resolver.resolve(topic_id)]
                except InputValidationError as exc:
                    issues.extend(
                        f"student '{group['email']}', preference {rank}: {issue}"
                        for issue in exc.issues
                    )
                    continue
                for language_rank, language in enumerate(
                    parse_languages(group[f"topic_preference_{rank}_languages"]),
                    start=1,
                ):
                    options.append(
                        _Option(
                            group=group_index,
                            topic_id=topic["topic_id"],
                            title=topic["topic_title"],
                            description=topic["topic_description"],
                            submitter_email=topic["submitter_email"],
                            capacity_key=topic["topic_id"],
                            rank=rank,
                            language=language,
                            language_rank=language_rank,
                            source="ranked_preference",
                        )
                    )
        elif path == "self_proposed":
            for language_rank, language in enumerate(
                parse_languages(group["self_proposed_thesis_language"]), start=1
            ):
                options.append(
                    _Option(
                        group=group_index,
                        topic_id=f"self:{group['thesis_group_id']}",
                        title=group["self_proposed_thesis_title"],
                        description=group["self_proposed_thesis_description"],
                        submitter_email="",
                        capacity_key=None,
                        rank=None,
                        language=language,
                        language_rank=language_rank,
                        source="self_proposed",
                    )
                )
        else:
            for language_rank, language in enumerate(
                parse_languages(group["carry_over_thesis_language"]), start=1
            ):
                title = group["carry_over_thesis_topic"]
                options.append(
                    _Option(
                        group=group_index,
                        topic_id=f"carry:{group['thesis_group_id']}",
                        title=title,
                        description=clean_text(
                            group.get("carry_over_thesis_description")
                        ),
                        submitter_email="",
                        capacity_key=None,
                        rank=None,
                        language=language,
                        language_rank=language_rank,
                        source="carry_over",
                    )
                )
    if issues:
        raise InputValidationError(issues)
    return options


def allocate_forms_submissions(
    submissions: pd.DataFrame,
    topics: pd.DataFrame,
    researchers: pd.DataFrame,
    backend: SimilarityBackend,
    *,
    duplicate_policy: str = "keep-last",
    allow_partial: bool = False,
    enforce_distinct_roles: bool = True,
) -> GroupedAllocationResult:
    """Jointly allocate thesis groups, ordered languages, and both roles.

    Objective stages are lexicographic. They preserve valid carry-over role
    assignments first, then minimize student-weighted topic rank, minimize
    student-weighted language rank, maximize topic-submitter assignments,
    satisfy workload minimums where feasible, and finally optimize semantic fit.
    """

    groups = normalize_forms_submissions(
        submissions, duplicate_policy=duplicate_policy
    )
    topic_table = normalize_topics(topics)
    researcher_table = normalize_researchers(researchers, require_capacities=True)
    researcher_table = researcher_table.sort_values("email").reset_index(drop=True)
    researcher_table["_profile_text"] = _candidate_text(researcher_table)
    groups, email_warnings = _resolve_carry_over_emails(groups, researcher_table)
    options = _build_options(groups, topic_table)

    option_by_group: dict[int, list[int]] = {index: [] for index in groups.index}
    for option_index, option in enumerate(options):
        option_by_group[option.group].append(option_index)

    variable_names: list[tuple[str, object]] = []
    lower: list[float] = []
    upper: list[float] = []
    integral: list[int] = []

    def variable(name: str, key: object, *, maximum: float = 1) -> int:
        index = len(variable_names)
        variable_names.append((name, key))
        lower.append(0)
        upper.append(maximum)
        integral.append(1)
        return index

    x = {option_index: variable("option", option_index) for option_index in range(len(options))}
    unassigned = {
        group_index: variable("unassigned", group_index)
        for group_index in groups.index
        if allow_partial
    }

    role_edges: dict[str, dict[tuple[int, int], int]] = {
        "daily_supervisor": {},
        "promotor": {},
    }
    similarities: dict[tuple[int, int], float] = {}
    if options and not researcher_table.empty:
        score_matrix = np.asarray(
            backend.score(
                [option.text for option in options],
                researcher_table["_profile_text"].tolist(),
            ),
            dtype=float,
        )
        expected = (len(options), len(researcher_table))
        if score_matrix.shape != expected:
            raise ValueError(
                f"Similarity backend returned {score_matrix.shape}; expected {expected}"
            )
    else:
        score_matrix = np.zeros((len(options), len(researcher_table)))

    for option_index, option in enumerate(options):
        for researcher_index, researcher in researcher_table.iterrows():
            compatible, _ = first_compatible_language(
                option.language, researcher["supervision_languages"]
            )
            if not compatible:
                continue
            raw = float(score_matrix[option_index, researcher_index])
            similarities[(option_index, researcher_index)] = raw if np.isfinite(raw) else 0.0
            for role, spec in ROLE_SPECS.items():
                if int(researcher[spec.maximum_column]) > 0:
                    role_edges[role][(option_index, researcher_index)] = variable(
                        role, (option_index, researcher_index)
                    )

    deficits: dict[tuple[str, int], int] = {}
    load_slots: dict[tuple[str, int, int], int] = {}
    for role, spec in ROLE_SPECS.items():
        for researcher_index, researcher in researcher_table.iterrows():
            minimum = int(researcher[spec.minimum_column])
            maximum = int(researcher[spec.maximum_column])
            for slot in range(maximum):
                load_slots[(role, researcher_index, slot)] = variable(
                    "load_slot", (role, researcher_index, slot)
                )
            if minimum > 0 and maximum > 0:
                deficits[(role, researcher_index)] = variable(
                    "minimum_deficit", (role, researcher_index), maximum=minimum
                )

    constraint_rows: list[dict[int, float]] = []
    constraint_lower: list[float] = []
    constraint_upper: list[float] = []

    def constrain(coefficients: dict[int, float], minimum: float, maximum: float) -> None:
        constraint_rows.append(coefficients)
        constraint_lower.append(minimum)
        constraint_upper.append(maximum)

    for group_index in groups.index:
        coefficients = {x[index]: 1 for index in option_by_group[group_index]}
        if allow_partial:
            coefficients[unassigned[group_index]] = 1
        constrain(coefficients, 1, 1)

    for option_index in range(len(options)):
        for role in ROLE_SPECS:
            coefficients = {x[option_index]: -1}
            coefficients.update(
                {
                    edge_variable: 1
                    for (edge_option, _), edge_variable in role_edges[role].items()
                    if edge_option == option_index
                }
            )
            constrain(coefficients, 0, 0)

    topic_capacity = topic_table.set_index("topic_id")["capacity"].to_dict()
    for topic_id, capacity in topic_capacity.items():
        coefficients = {
            x[index]: 1
            for index, option in enumerate(options)
            if option.capacity_key == topic_id
        }
        if coefficients:
            constrain(coefficients, -np.inf, int(capacity))

    for role, spec in ROLE_SPECS.items():
        for researcher_index, researcher in researcher_table.iterrows():
            coefficients = {
                edge_variable: 1
                for (option_index, candidate_index), edge_variable in role_edges[role].items()
                if candidate_index == researcher_index
            }
            constrain(
                coefficients,
                -np.inf,
                int(researcher[spec.maximum_column]),
            )
            load_equation = dict(coefficients)
            for slot in range(int(researcher[spec.maximum_column])):
                load_equation[load_slots[(role, researcher_index, slot)]] = -1
            constrain(load_equation, 0, 0)
            deficit = deficits.get((role, researcher_index))
            if deficit is not None:
                coefficients = dict(coefficients)
                coefficients[deficit] = 1
                constrain(
                    coefficients,
                    int(researcher[spec.minimum_column]),
                    np.inf,
                )

    if enforce_distinct_roles:
        for group_index in groups.index:
            group_options = set(option_by_group[group_index])
            for researcher_index in researcher_table.index:
                coefficients = {
                    edge_variable: 1
                    for role in ROLE_SPECS
                    for (option_index, candidate_index), edge_variable in role_edges[role].items()
                    if option_index in group_options and candidate_index == researcher_index
                }
                if coefficients:
                    constrain(coefficients, -np.inf, 1)

    variable_count = len(variable_names)

    def objective() -> np.ndarray:
        return np.zeros(variable_count, dtype=float)

    stages: list[np.ndarray] = []
    if allow_partial:
        for path in ("carry_over", "self_proposed"):
            cost = objective()
            for group_index, variable_index in unassigned.items():
                if groups.at[group_index, "allocation_path"] == path:
                    cost[variable_index] = int(groups.at[group_index, "group_size"])
            stages.append(cost)
        cost = objective()
        for group_index, variable_index in unassigned.items():
            cost[variable_index] = int(groups.at[group_index, "group_size"])
        stages.append(cost)

    carry_retention = objective()
    warnings: list[str] = list(email_warnings)
    researcher_by_email = {
        row["email"]: index for index, row in researcher_table.iterrows()
    }
    for option_index, option in enumerate(options):
        group = groups.loc[option.group]
        if option.source != "carry_over":
            continue
        desired = {
            "daily_supervisor": group["resolved_daily_supervisor_email"],
            "promotor": group["resolved_thesis_promotor_email"],
        }
        for role, email in desired.items():
            if not email:
                continue
            researcher_index = researcher_by_email.get(email)
            edge = role_edges[role].get((option_index, researcher_index)) if researcher_index is not None else None
            if edge is not None:
                carry_retention[edge] = -1
    stages.append(carry_retention)

    topic_cost = objective()
    language_cost = objective()
    for option_index, option in enumerate(options):
        group_size = int(groups.at[option.group, "group_size"])
        topic_cost[x[option_index]] = (option.rank or 0) * group_size
        language_cost[x[option_index]] = (option.language_rank - 1) * group_size
    stages.extend((topic_cost, language_cost))

    submitter_cost = objective()
    for role in ROLE_SPECS:
        for (option_index, researcher_index), variable_index in role_edges[role].items():
            submitter = options[option_index].submitter_email
            if submitter and researcher_table.at[researcher_index, "email"] == submitter:
                submitter_cost[variable_index] = -1
    stages.append(submitter_cost)

    minimum_cost = objective()
    for variable_index in deficits.values():
        minimum_cost[variable_index] = 1
    stages.append(minimum_cost)

    semantic_cost = objective()
    for role in ROLE_SPECS:
        for (option_index, researcher_index), variable_index in role_edges[role].items():
            similarity = min(1.0, max(-1.0, similarities[(option_index, researcher_index)]))
            semantic_cost[variable_index] = (1.0 - similarity) * 1_000 + researcher_index * 1e-4
    for (_role, _researcher_index, slot), variable_index in load_slots.items():
        semantic_cost[variable_index] = 25 * slot
    stages.append(semantic_cost)

    def linear_constraints() -> LinearConstraint:
        row_indices: list[int] = []
        column_indices: list[int] = []
        values: list[float] = []
        for row_index, coefficients in enumerate(constraint_rows):
            for column_index, value in coefficients.items():
                row_indices.append(row_index)
                column_indices.append(column_index)
                values.append(value)
        matrix = coo_matrix(
            (values, (row_indices, column_indices)),
            shape=(len(constraint_rows), variable_count),
        ).tocsr()
        return LinearConstraint(matrix, constraint_lower, constraint_upper)

    solution = None
    for stage in stages:
        if not np.any(stage):
            continue
        solution = milp(
            c=stage,
            integrality=np.asarray(integral),
            bounds=Bounds(lower, upper),
            constraints=linear_constraints(),
            options={"presolve": True},
        )
        if not solution.success or solution.x is None:
            raise InfeasibleAssignmentError(
                "A complete group, topic, language, and supervisor allocation is impossible. "
                "Check topic capacities, researcher role capacities, language compatibility, "
                "and the distinct-role rule."
            )
        optimum = float(stage @ solution.x)
        rounded = round(optimum)
        if np.allclose(stage, np.round(stage)) and abs(optimum - rounded) < 1e-6:
            optimum = float(rounded)
        tolerance = 1e-6 if np.allclose(stage, np.round(stage)) else 1e-5
        constrain(
            {index: float(value) for index, value in enumerate(stage) if value},
            optimum - tolerance,
            optimum + tolerance,
        )

    if solution is None:
        solution = milp(
            c=objective(),
            integrality=np.asarray(integral),
            bounds=Bounds(lower, upper),
            constraints=linear_constraints(),
            options={"presolve": True},
        )
        if not solution.success or solution.x is None:
            raise InfeasibleAssignmentError(
                "A complete group, topic, language, and supervisor allocation is impossible."
            )

    selected_options = {
        option_index for option_index, variable_index in x.items() if solution.x[variable_index] > 0.5
    }
    group_rows: list[dict[str, object]] = []
    for group_index, group in groups.iterrows():
        selected = [index for index in option_by_group[group_index] if index in selected_options]
        row = group.to_dict()
        for spec in ROLE_SPECS.values():
            row[spec.name_column] = ""
            row[spec.email_column] = ""
            row[spec.score_column] = pd.NA
            row[spec.source_column] = ""
        if not selected:
            row.update(
                {
                    "assigned_topic_id": pd.NA,
                    "assigned_topic": pd.NA,
                    "assigned_topic_description": pd.NA,
                    "assigned_rank": pd.NA,
                    "assigned_cost": pd.NA,
                    "group_preference_cost": pd.NA,
                    "assigned_language": pd.NA,
                    "assigned_language_rank": pd.NA,
                    "topic_assignment_source": "unassigned",
                }
            )
            group_rows.append(row)
            continue
        option_index = selected[0]
        option = options[option_index]
        row.update(
            {
                "assigned_topic_id": option.topic_id,
                "assigned_topic": option.title,
                "assigned_topic_description": option.description,
                "assigned_rank": option.rank if option.rank is not None else pd.NA,
                "assigned_cost": option.rank if option.rank is not None else pd.NA,
                "group_preference_cost": (option.rank or 0) * int(group["group_size"]),
                "assigned_language": option.language,
                "assigned_language_rank": option.language_rank,
                "topic_assignment_source": option.source,
            }
        )
        for role, spec in ROLE_SPECS.items():
            chosen = [
                researcher_index
                for (edge_option, researcher_index), variable_index in role_edges[role].items()
                if edge_option == option_index and solution.x[variable_index] > 0.5
            ]
            if not chosen:
                continue
            researcher_index = chosen[0]
            researcher = researcher_table.loc[researcher_index]
            row[spec.name_column] = researcher["full_name"]
            row[spec.email_column] = researcher["email"]
            row[spec.score_column] = round(similarities[(option_index, researcher_index)], 6)
            audit_email_column, review_prefix, review_label = ROLE_AUDIT_FIELDS[role]
            desired = clean_text(group[audit_email_column])
            if option.source == "carry_over" and researcher["email"] == desired:
                source = "carry_over"
            elif option.submitter_email and researcher["email"] == option.submitter_email:
                source = "topic_submitter"
            else:
                source = "semantic"
            row[spec.source_column] = source
            if option.source != "carry_over":
                continue
            if not desired and clean_text(row[f"{review_prefix}_review_status"]):
                replacement = (
                    f"Automatically assigned {review_label.lower()} replacement: "
                    f"'{researcher['email']}'."
                )
                row[f"{review_prefix}_review_reason"] = _append_review_reason(
                    row[f"{review_prefix}_review_reason"], replacement
                )
                row["carry_over_review_reason"] = _append_review_reason(
                    row["carry_over_review_reason"], replacement
                )
            elif desired and researcher["email"] != desired:
                review_status = (
                    f"{MANUAL_REVIEW_NEEDED} - {review_label} REASSIGNED"
                )
                reason = (
                    f"Resolved {review_label.lower()} '{desired}' could not be retained "
                    "under the current eligibility, language, distinct-role, and maximum-"
                    f"capacity constraints. Assigned replacement: '{researcher['email']}'."
                )
                row[f"{review_prefix}_review_status"] = review_status
                row[f"{review_prefix}_review_reason"] = reason
                row["carry_over_review_status"] = _append_review_reason(
                    row["carry_over_review_status"], review_status
                )
                row["carry_over_review_reason"] = _append_review_reason(
                    row["carry_over_review_reason"], reason
                )
                warnings.append(
                    f"Carry-over thesis '{group['thesis_group_id']}': "
                    f"{review_status}. {reason}"
                )
        group_rows.append(row)

    group_assignments = pd.DataFrame(group_rows)
    leading_columns = [
        "full_name",
        "email",
        "student_number",
        "thesis_group_id",
        "carry_over_review_status",
        "daily_supervisor_review_status",
        "thesis_promotor_review_status",
        "daily_supervisor_review_reason",
        "thesis_promotor_review_reason",
        "carry_over_review_reason",
    ]
    group_assignments = group_assignments.loc[
        :,
        [
            *[column for column in leading_columns if column in group_assignments],
            *[column for column in group_assignments if column not in leading_columns],
        ],
    ]
    assigned_groups = group_assignments["topic_assignment_source"].ne("unassigned")
    if (~assigned_groups).any():
        warnings.append(
            f"Partial allocation: {int((~assigned_groups).sum())} thesis group(s) remain unassigned"
        )
    for role, spec in ROLE_SPECS.items():
        counts = group_assignments.loc[assigned_groups, spec.email_column].value_counts()
        for _, researcher in researcher_table.iterrows():
            minimum = int(researcher[spec.minimum_column])
            assigned = int(counts.get(researcher["email"], 0))
            if assigned < minimum:
                warnings.append(
                    f"{spec.label} minimum target remains unmet: "
                    f"{researcher['full_name']} ({assigned}/{minimum})"
                )

    workload_input = group_assignments.loc[assigned_groups].copy()
    summary = build_workload_summary(workload_input, researcher_table)
    expanded = expand_group_assignments(group_assignments)
    assigned_students = int(
        group_assignments.loc[assigned_groups, "group_size"].astype(int).sum()
    )
    return GroupedAllocationResult(
        assignments=expanded,
        group_assignments=group_assignments.drop(columns=["_form_order"], errors="ignore"),
        summary=summary,
        preference_cost=int(
            group_assignments.loc[assigned_groups, "group_preference_cost"].fillna(0).sum()
        ),
        assigned_students=assigned_students,
        assigned_theses=int(assigned_groups.sum()),
        carry_over_theses=int(
            (group_assignments.loc[assigned_groups, "allocation_path"] == "carry_over").sum()
        ),
        self_proposed_theses=int(
            (group_assignments.loc[assigned_groups, "allocation_path"] == "self_proposed").sum()
        ),
        dual_theses=int(
            (group_assignments.loc[assigned_groups, "submission_type"] == "dual").sum()
        ),
        manual_review_theses=int(
            group_assignments["carry_over_review_status"]
            .fillna("")
            .astype(str)
            .str.strip()
            .ne("")
            .sum()
        ),
        warnings=tuple(dict.fromkeys(warnings)),
    )
