"""Creation of input workbooks with the canonical column contracts."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from thesis_allocation.errors import InputValidationError
from thesis_allocation.io import write_table


TEMPLATE_COLUMNS = {
    "researchers.xlsx": [
        "full_name",
        "email",
        "appointment_type",
        "appointment_percentage",
        "comment",
        "timestamp",
        "supervision_languages",
        "profile_url",
        "publications_url",
        "profile_description",
        "publication_list",
        "daily_supervisor_minimum_theses",
        "daily_supervisor_maximum_theses",
        "promotor_minimum_theses",
        "promotor_maximum_theses",
    ],
    "topics.xlsx": [
        "topic_id",
        "topic_title",
        "topic_description",
        "submitter_email",
        "capacity",
    ],
    "student_preferences.xlsx": [
        "full_name",
        "Email",
        "student_number",
        "thesis_type",
        "partner_full_name",
        "partner_email",
        "partner_student_number",
        "dual_thesis_confirmation",
        "thesis_allocation_status",
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
    ],
}


def create_templates(
    output_directory: str | Path,
    *,
    force: bool = False,
) -> tuple[Path, ...]:
    """Create the three standard input templates."""

    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    targets = [directory / filename for filename in TEMPLATE_COLUMNS]
    existing = [str(path) for path in targets if path.exists()]
    if existing and not force:
        raise InputValidationError(
            "Template file(s) already exist; use --force to replace them: "
            + ", ".join(existing)
        )

    for path in targets:
        write_table(pd.DataFrame(columns=TEMPLATE_COLUMNS[path.name]), path)
    return tuple(targets)
