#!/usr/bin/env python3
"""Build the Google Colab notebook deterministically."""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = ROOT / "notebooks" / "Thesis_Allocation_Colab.ipynb"


def _source(text: str) -> list[str]:
    normalized = textwrap.dedent(text).strip("\n") + "\n"
    return normalized.splitlines(keepends=True)


def _markdown(text: str) -> dict[str, object]:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": _source(text),
    }


def _code(text: str, *, cell_id: str, form: bool = False) -> dict[str, object]:
    metadata: dict[str, object] = {"id": cell_id}
    if form:
        metadata["cellView"] = "form"
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": metadata,
        "outputs": [],
        "source": _source(text),
    }


def build_notebook() -> dict[str, object]:
    """Return the complete notebook document."""

    cells = [
        _markdown(
            """
            # Thesis allocation

            [![GitHub repository](https://img.shields.io/badge/source-GitHub-181717?logo=github)](https://github.com/christofkoolen/computational-allocation-of-thesis-supervision)

            This notebook runs the thesis allocation without installing anything on
            your computer.

            **How to use it**

            1. Review the options below.
            2. Select **Runtime → Run all**.
            3. When prompted, upload the requested Excel or CSV files together.
            4. Wait for the results ZIP to download.

            The complete-allocation workflow expects researcher, topic, and student
            preference files. The reassignment workflow expects the previous final
            assignments, researcher file, and topic file.

            **Data notice:** uploaded files are processed in a Google Colab virtual
            machine. This notebook does not mount Google Drive and does not save input
            data in notebook output. Use real student data only when this processing
            arrangement has been approved by your institution.
            """
        ),
        _code(
            """
            # @title 1. Choose the task and options
            task = "Complete allocation"  # @param ["Complete allocation", "Reassign supervision"]
            matching_method = "Semantic matching (recommended)"  # @param ["Semantic matching (recommended)", "Fast lexical matching"]
            retrieve_researcher_profiles = False  # @param {type:"boolean"}
            allow_partial_results = False  # @param {type:"boolean"}
            allow_same_person_for_both_roles = False  # @param {type:"boolean"}
            duplicate_student_submissions = "Keep last submission"  # @param ["Keep last submission", "Keep first submission", "Stop with an error"]

            # These three settings are used only for reassignment.
            reassignment_role = "Daily supervisor"  # @param ["Daily supervisor", "Promotor"]
            reassignment_scope = "One student"  # @param ["One student", "Everyone assigned to a departing supervisor"]
            target_email = ""  # @param {type:"string"}
            """,
            cell_id="options",
            form=True,
        ),
        _code(
            """
            # @title 2. Prepare the allocation program
            import subprocess
            import sys

            repository = (
                "git+https://github.com/christofkoolen/"
                "computational-allocation-of-thesis-supervision.git@main"
            )
            package = (
                f"computational-thesis-allocation[semantic] @ {repository}"
                if matching_method.startswith("Semantic")
                else f"computational-thesis-allocation @ {repository}"
            )
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--quiet",
                    "--no-cache-dir",
                    package,
                ],
                check=True,
            )
            print("The allocation program is ready.")
            """,
            cell_id="setup",
            form=True,
        ),
        _code(
            """
            # @title 3. Upload the files and run
            import json
            import os
            import shutil
            import zipfile
            from pathlib import Path

            import pandas as pd
            from google.colab import files

            from thesis_allocation.cli import main as run_command
            from thesis_allocation.schema import (
                ASSIGNMENT_ALIASES,
                PREFERENCE_ALIASES,
                RESEARCHER_ALIASES,
                TOPIC_ALIASES,
            )


            def normalized_columns(frame):
                return {str(column).strip().casefold() for column in frame.columns}


            def aliases_for(canonical, aliases):
                return {canonical.casefold(), *(alias.casefold() for alias in aliases)}


            def read_uploaded_table(path):
                suffix = path.suffix.casefold()
                if suffix == ".xlsx":
                    return pd.read_excel(path)
                if suffix == ".csv":
                    return pd.read_csv(path)
                if suffix == ".tsv":
                    return pd.read_csv(path, sep="\\t")
                raise ValueError(
                    f"{path.name} is not supported. Use .xlsx, .csv, or .tsv."
                )


            def classify_upload(path):
                columns = normalized_columns(read_uploaded_table(path))
                preference_columns = aliases_for(
                    "preference_1", PREFERENCE_ALIASES["preference_1"]
                )
                assignment_specific = set()
                for canonical in (
                    "daily_supervisor",
                    "daily_supervisor_email",
                    "promotor",
                    "promotor_email",
                ):
                    assignment_specific.update(
                        aliases_for(canonical, ASSIGNMENT_ALIASES[canonical])
                    )
                topic_columns = aliases_for(
                    "topic_title", TOPIC_ALIASES["topic_title"]
                )
                researcher_specific = set()
                for canonical in (
                    "appointment",
                    "profile_url",
                    "publications_url",
                    "profile_description",
                    "publication_list",
                    "daily_supervisor_minimum_theses",
                    "daily_supervisor_maximum_theses",
                    "promotor_minimum_theses",
                    "promotor_maximum_theses",
                ):
                    researcher_specific.update(
                        aliases_for(canonical, RESEARCHER_ALIASES[canonical])
                    )

                if columns.intersection(preference_columns):
                    return "preferences"
                if columns.intersection(assignment_specific):
                    return "assignments"
                if columns.intersection(topic_columns):
                    return "topics"
                if columns.intersection(researcher_specific):
                    return "researchers"
                return None


            def identify_uploads(paths, required_kinds):
                identified = {}
                problems = []
                for path in paths:
                    try:
                        kind = classify_upload(path)
                    except Exception as exc:
                        problems.append(f"{path.name}: {exc}")
                        continue
                    if kind is None:
                        problems.append(
                            f"{path.name}: the columns do not identify a supported input."
                        )
                    elif kind in identified:
                        problems.append(
                            f"{path.name}: another uploaded file was already identified "
                            f"as {kind}."
                        )
                    else:
                        identified[kind] = path

                missing = sorted(set(required_kinds).difference(identified))
                if missing:
                    problems.append("Missing input type(s): " + ", ".join(missing))
                if problems:
                    raise ValueError("\\n".join(problems))
                return identified


            runtime_root = Path(os.environ.get("COLAB_RUNTIME_ROOT", "/content"))
            run_root = runtime_root / "thesis_allocation_run"
            input_directory = run_root / "input"
            output_directory = run_root / "output"
            shutil.rmtree(run_root, ignore_errors=True)
            input_directory.mkdir(parents=True)
            output_directory.mkdir(parents=True)

            print("Select the three input files together in the upload window.")
            previous_directory = Path.cwd()
            os.chdir(input_directory)
            try:
                uploaded = files.upload()
            finally:
                os.chdir(previous_directory)

            uploaded_paths = [input_directory / name for name in uploaded]
            backend = (
                "sentence-transformers"
                if matching_method.startswith("Semantic")
                else "tfidf"
            )
            common_options = ["--backend", backend]
            if allow_partial_results:
                common_options.append("--allow-partial")
            if allow_same_person_for_both_roles:
                common_options.append("--allow-same-person")

            if task == "Complete allocation":
                inputs = identify_uploads(
                    uploaded_paths,
                    {"researchers", "topics", "preferences"},
                )
                duplicate_policy = {
                    "Keep last submission": "keep-last",
                    "Keep first submission": "keep-first",
                    "Stop with an error": "error",
                }[duplicate_student_submissions]
                arguments = [
                    "run",
                    "--researchers",
                    str(inputs["researchers"]),
                    "--topics",
                    str(inputs["topics"]),
                    "--preferences",
                    str(inputs["preferences"]),
                    "--output-directory",
                    str(output_directory),
                    "--duplicate-policy",
                    duplicate_policy,
                    *common_options,
                ]
                if not retrieve_researcher_profiles:
                    arguments.append("--skip-scrape")
                result_filename = "thesis_allocation_results.zip"
            else:
                if not target_email.strip():
                    raise ValueError(
                        "Enter the student or departing supervisor email in "
                        "'target_email' before running reassignment."
                    )
                inputs = identify_uploads(
                    uploaded_paths,
                    {"assignments", "researchers", "topics"},
                )
                role = (
                    "daily_supervisor"
                    if reassignment_role == "Daily supervisor"
                    else "promotor"
                )
                target_option = (
                    "--student-email"
                    if reassignment_scope == "One student"
                    else "--departing-supervisor-email"
                )
                arguments = [
                    "reassign",
                    "--assignments",
                    str(inputs["assignments"]),
                    "--researchers",
                    str(inputs["researchers"]),
                    "--topics",
                    str(inputs["topics"]),
                    "--role",
                    role,
                    target_option,
                    target_email.strip(),
                    "--output",
                    str(output_directory / "final_assignments_reassigned.xlsx"),
                    "--summary-output",
                    str(output_directory / "supervisor_summary_reassigned.xlsx"),
                    "--log-output",
                    str(output_directory / "reassignment_log.csv"),
                    *common_options,
                ]
                result_filename = "thesis_reassignment_results.zip"

            try:
                exit_code = run_command(arguments)
                if exit_code != 0:
                    raise RuntimeError(
                        "The run stopped because an input or constraint was invalid. "
                        "Read the message immediately above for the exact reason."
                    )
            finally:
                shutil.rmtree(input_directory, ignore_errors=True)

            result_path = run_root / result_filename
            with zipfile.ZipFile(
                result_path,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
            ) as archive:
                for path in sorted(output_directory.iterdir()):
                    archive.write(path, arcname=path.name)

            if task == "Complete allocation":
                report = json.loads(
                    (output_directory / "run_report.json").read_text(encoding="utf-8")
                )
                print(
                    f"Completed: {report['assigned_students']} student(s), "
                    f"total preference cost {report['preference_cost']}."
                )
                for warning in report["warnings"]:
                    print(f"Warning: {warning}")
            else:
                log = pd.read_csv(output_directory / "reassignment_log.csv")
                completed = (
                    log["new_supervisor_email"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .ne("")
                )
                print(f"Completed: {int(completed.sum())} reassignment(s).")

            print(f"Downloading {result_filename}...")
            files.download(str(result_path))
            """,
            cell_id="run",
        ),
        _markdown(
            """
            ## When finished

            Select **Runtime → Disconnect and delete runtime**. This removes the
            temporary Colab virtual machine, including generated result files.

            If the download did not start automatically, open the folder icon on the
            left, find the results ZIP under `thesis_allocation_run`, and download it.
            """
        ),
        _code(
            """
            # @title Optional: download blank input templates
            download_blank_templates = False  # @param {type:"boolean"}

            if download_blank_templates:
                import os
                import shutil
                from pathlib import Path

                from google.colab import files
                from thesis_allocation.templates import create_templates

                runtime_root = Path(os.environ.get("COLAB_RUNTIME_ROOT", "/content"))
                template_directory = runtime_root / "thesis_allocation_templates"
                shutil.rmtree(template_directory, ignore_errors=True)
                template_directory.mkdir(parents=True)
                create_templates(template_directory)
                template_zip = runtime_root / "thesis_allocation_input_templates.zip"
                shutil.make_archive(
                    str(template_zip.with_suffix("")),
                    "zip",
                    template_directory,
                )
                files.download(str(template_zip))
            """,
            cell_id="templates",
        ),
    ]

    return {
        "cells": cells,
        "metadata": {
            "colab": {
                "name": NOTEBOOK_PATH.name,
                "provenance": [],
            },
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
            "thesis_allocation": {
                "generated_by": "scripts/build_colab_notebook.py",
                "package_source": (
                    "https://github.com/christofkoolen/"
                    "computational-allocation-of-thesis-supervision"
                ),
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def notebook_bytes() -> bytes:
    """Serialize the generated notebook with stable formatting."""

    return (
        json.dumps(
            build_notebook(),
            indent=1,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the committed notebook is not up to date.",
    )
    args = parser.parse_args()

    expected = notebook_bytes()
    if args.check:
        if not NOTEBOOK_PATH.is_file() or NOTEBOOK_PATH.read_bytes() != expected:
            print(
                "The Colab notebook is stale. Run scripts/build_colab_notebook.py.",
                file=sys.stderr,
            )
            return 1
        print("The Colab notebook is up to date.")
        return 0

    NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTEBOOK_PATH.write_bytes(expected)
    print(NOTEBOOK_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
