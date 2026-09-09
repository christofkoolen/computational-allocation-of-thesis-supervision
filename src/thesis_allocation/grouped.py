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
from thesis_allocation.schema import clean_text, normalize_researchers, normalize_topics
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
    warnings: tuple[str, ...] = ()


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
    warnings: list[str] = []
    researcher_by_email = {
        row["email"]: index for index, row in researcher_table.iterrows()
    }
    for option_index, option in enumerate(options):
        group = groups.loc[option.group]
        if option.source != "carry_over":
            continue
        desired = {
            "daily_supervisor": group["daily_supervisor_email"],
            "promotor": group["thesis_promotor_email"],
        }
        for role, email in desired.items():
            researcher_index = researcher_by_email.get(email)
            edge = role_edges[role].get((option_index, researcher_index)) if researcher_index is not None else None
            if edge is None:
                warnings.append(
                    f"Carry-over thesis '{group['thesis_group_id']}': requested {role.replace('_', ' ')} "
                    f"'{email}' is unavailable, ineligible, or language-incompatible and will be reassigned"
                )
            else:
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
            desired = (
                group["daily_supervisor_email"]
                if role == "daily_supervisor"
                else group["thesis_promotor_email"]
            )
            if option.source == "carry_over" and researcher["email"] == desired:
                source = "carry_over"
            elif option.submitter_email and researcher["email"] == option.submitter_email:
                source = "topic_submitter"
            else:
                source = "semantic"
            row[spec.source_column] = source
        group_rows.append(row)

    group_assignments = pd.DataFrame(group_rows)
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
        warnings=tuple(dict.fromkeys(warnings)),
    )
