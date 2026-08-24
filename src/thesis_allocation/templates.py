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
        "appointment",
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
        "supervision_languages",
    ],
    "student_preferences.xlsx": [
        "full_name",
        "email",
        "preference_1",
        "preference_1_languages",
        "preference_2",
        "preference_2_languages",
        "preference_3",
        "preference_3_languages",
        "own_topic_description",
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
