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
    return {"cell_type": "markdown", "metadata": {}, "source": _source(text)}


def _code(text: str, *, cell_id: str, form: bool = False) -> dict[str, object]:
    metadata: dict[str, object] = {"id": cell_id}
    if form:
        metadata["cellView"] = "form"
    return {"cell_type": "code", "execution_count": None, "metadata": metadata, "outputs": [], "source": _source(text)}


def build_notebook() -> dict[str, object]:
    cells = [
        _markdown('''
        # Thesis allocation

        [![GitHub repository](https://img.shields.io/badge/source-GitHub-181717?logo=github)](https://github.com/christofkoolen/computational-allocation-of-thesis-supervision)

        This notebook runs the thesis allocation without installing anything on
        your computer.

        Work through the numbered sections below:

        1. optionally download blank input files;
        2. choose and configure one of the two workflows;
        3. run the selected workflow.

        If you already have the required input files, skip section 1.

        **Data notice:** uploaded files are processed in a Google Colab virtual
        machine. This notebook does not mount Google Drive and does not save input
        data in notebook output.
        '''),
        _markdown('''
        ## 1. Optional: download blank input files

        The complete allocation uses three files:

        1. `researchers.xlsx`
        2. `topics.xlsx`
        3. `student_preferences.xlsx`

        Skip this section if these files are already prepared. The third file
        contains the submission type and allocation route, including ranked,
        self-proposed, carry-over, and dual-thesis details.

        In `researchers.xlsx`, `appointment_type` and the other metadata columns are
        descriptive only. Eligibility for daily-supervisor and promotor roles is
        controlled by the corresponding maximum-capacity columns: a maximum above
        `0` means eligible and `0` means ineligible. The minimum columns are workload
        targets, not role categories.

        In `topics.xlsx`, a blank `capacity` cell means `1`. Enter a larger whole
        number only when more than one thesis may receive that offered topic.
        '''),
        _code('''
        # @title 1. Download blank input files (optional)
        download_blank_templates = False  # @param {type:"boolean"}

        if download_blank_templates:
            import os
            import shutil
            from pathlib import Path

            import pandas as pd
            from google.colab import files

            template_columns = {
                "researchers.xlsx": [
                    "full_name", "email", "appointment_type", "appointment_percentage",
                    "comment", "timestamp", "supervision_languages", "profile_url", "publications_url", "profile_description",
                    "publication_list", "daily_supervisor_minimum_theses",
                    "daily_supervisor_maximum_theses", "promotor_minimum_theses", "promotor_maximum_theses",
                ],
                "topics.xlsx": [
                    "topic_id", "topic_title", "topic_description",
                    "submitter_email", "capacity",
                ],
                "student_preferences.xlsx": [
                    "full_name", "email", "student_number", "thesis_type",
                    "partner_full_name", "partner_email", "partner_student_number",
                    "dual_thesis_confirmation", "thesis_allocation_status",
                    "topic_preference_1", "topic_preference_1_languages",
                    "topic_preference_2", "topic_preference_2_languages",
                    "topic_preference_3", "topic_preference_3_languages",
                    "self_proposed_thesis_title", "self_proposed_thesis_description",
                    "self_proposed_thesis_language", "carry_over_thesis_topic",
                    "carry_over_thesis_description", "carry_over_thesis_language",
                    "daily_supervisor_email", "thesis_promotor_email",
                ],
            }

            runtime_root = Path(os.environ.get("COLAB_RUNTIME_ROOT", "/content"))
            template_directory = runtime_root / "thesis_allocation_templates"
            shutil.rmtree(template_directory, ignore_errors=True)
            template_directory.mkdir(parents=True)
            for filename, columns in template_columns.items():
                pd.DataFrame(columns=columns).to_excel(template_directory / filename, index=False)
            template_zip = runtime_root / "thesis_allocation_input_templates.zip"
            shutil.make_archive(str(template_zip.with_suffix("")), "zip", template_directory)
            files.download(str(template_zip))
        ''', cell_id='templates', form=True),
        _markdown('''
        ## 2. Choose a workflow

        Select one workflow and review only the options for that workflow. The
        notebook will use the selection below when section 3 runs.
        '''),
        _code('''
        # @title 2. Choose workflow
        task = "Complete allocation"  # @param ["Complete allocation", "Reassign supervision"]
        ''', cell_id='workflow', form=True),
        _markdown('''
        ### 2.a Workflow 1: thesis topic and supervision allocation

        Use **Complete allocation** for the normal annual allocation. Upload the
        three standard files together. The program routes ranked, self-proposed,
        and carry-over submissions from `student_preferences.xlsx`. A dual pair is
        treated as one thesis for topic and supervision capacity while both
        students remain represented in the preference cost.

        Languages are ordered alternatives. The optimizer tries to retain the
        highest listed language that is feasible within the topic and supervision
        constraints.
        '''),
        _code('''
        # @title 2.a Workflow 1 options
        matching_method = "Semantic matching (multilingual, recommended)"  # @param ["Semantic matching (multilingual, recommended)", "Lexical matching (fast)"]
        retrieve_researcher_profiles = False  # @param {type:"boolean"}
        allow_partial_results = False  # @param {type:"boolean"}
        allow_same_person_for_both_roles = False  # @param {type:"boolean"}
        duplicate_student_submissions = "Keep last submission"  # @param ["Keep last submission", "Keep first submission", "Stop with an error"]
        ''', cell_id='allocation-options', form=True),
        _markdown('''
        ### 2.b Workflow 2: reassignment

        Use **Reassign supervision** to replace one student's daily supervisor or
        promotor, or to replace all assignments held by a departing researcher.

        For **One student**, fill in `student_email`. For **Everyone assigned to a
        departing supervisor**, fill in `departing_researcher_email`. Only the
        field matching the selected scope is used. Carry-over and self-proposed
        topics remain reassignable even when they are absent from the offered-topic
        file.
        '''),
        _code('''
        # @title 2.b Workflow 2 options
        reassignment_role = "Daily supervisor"  # @param ["Daily supervisor", "Promotor"]
        reassignment_scope = "One student"  # @param ["One student", "Everyone assigned to a departing supervisor"]
        student_email = ""  # @param {type:"string"}
        departing_researcher_email = ""  # @param {type:"string"}
        ''', cell_id='reassignment-options', form=True),
        _markdown('''
        ## 3. Run the selected workflow

        After choosing the workflow and its options above, run the notebook. For
        complete allocation, upload the three standard files. Reassignment also
        uses three files. The notebook requests a GPU runtime for multilingual
        semantic matching, reports the assigned device, and explains how to select
        a T4 GPU if Colab provides a CPU instead.
        '''),
        _code('''
        # @title 3.a Prepare the allocation program
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
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--no-cache-dir", package], check=True)
        if matching_method.startswith("Semantic"):
            import torch

            if torch.cuda.is_available():
                print(f"The allocation program is ready. GPU detected: {torch.cuda.get_device_name(0)}")
            else:
                print(
                    "WARNING: No GPU was assigned. BGE-M3 will run on the CPU and may be slow. "
                    "Choose Runtime > Change runtime type > T4 GPU, then run the notebook again."
                )
        else:
            print("The allocation program is ready. Lexical matching uses the CPU.")
        ''', cell_id='setup', form=True),
        _code('''
        # @title 3.b Run selected workflow
        import json
        import os
        import shutil
        import zipfile
        from pathlib import Path

        import pandas as pd
        from google.colab import files

        from thesis_allocation.cli import main as run_command
        from thesis_allocation.schema import ASSIGNMENT_ALIASES, PREFERENCE_ALIASES, RESEARCHER_ALIASES, TOPIC_ALIASES

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
            raise ValueError(f"{path.name} is not supported. Use .xlsx, .csv, or .tsv.")

        def classify_upload(path):
            columns = normalized_columns(read_uploaded_table(path))
            if {"thesis_type", "thesis_allocation_status"}.issubset(columns):
                return "preferences"
            preference_columns = aliases_for("preference_1", PREFERENCE_ALIASES["preference_1"])
            assignment_specific = set()
            for canonical in ("daily_supervisor", "daily_supervisor_email", "promotor", "promotor_email"):
                assignment_specific.update(aliases_for(canonical, ASSIGNMENT_ALIASES[canonical]))
            topic_columns = aliases_for("topic_id", TOPIC_ALIASES["topic_id"])
            researcher_specific = set()
            for canonical in (
                "appointment", "supervision_languages", "profile_url",
                "publications_url", "profile_description", "publication_list",
                "daily_supervisor_minimum_theses",
                "daily_supervisor_maximum_theses", "promotor_minimum_theses",
                "promotor_maximum_theses",
            ):
                researcher_specific.update(aliases_for(canonical, RESEARCHER_ALIASES[canonical]))
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
                    problems.append(f"{path.name}: the columns do not identify a supported input.")
                elif kind in identified:
                    problems.append(f"{path.name}: another uploaded file was already identified as {kind}.")
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

        if task == "Complete allocation":
            print(
                "Select 1. researchers.xlsx, 2. topics.xlsx, and "
                "3. student_preferences.xlsx together."
            )
        else:
            print("Select the previous assignments, researchers, and topics together.")
        previous_directory = Path.cwd()
        os.chdir(input_directory)
        try:
            uploaded = files.upload()
        finally:
            os.chdir(previous_directory)

        uploaded_paths = [input_directory / name for name in uploaded]
        backend = "sentence-transformers" if matching_method.startswith("Semantic") else "tfidf"
        common_options = ["--backend", backend]
        if allow_partial_results:
            common_options.append("--allow-partial")
        if allow_same_person_for_both_roles:
            common_options.append("--allow-same-person")

        if task == "Complete allocation":
            inputs = identify_uploads(uploaded_paths, {"researchers", "topics", "preferences"})
            duplicate_policy = {
                "Keep last submission": "keep-last",
                "Keep first submission": "keep-first",
                "Stop with an error": "error",
            }[duplicate_student_submissions]
            arguments = [
                "run", "--researchers", str(inputs["researchers"]),
                "--topics", str(inputs["topics"]), "--preferences", str(inputs["preferences"]),
                "--output-directory", str(output_directory), "--duplicate-policy", duplicate_policy,
                *common_options,
            ]
            if "assignments" in inputs:
                arguments.extend(
                    ["--previous-final-assignments", str(inputs["assignments"])]
                )
            if not retrieve_researcher_profiles:
                arguments.append("--skip-scrape")
            result_filename = "thesis_allocation_results.zip"
        else:
            role = "daily_supervisor" if reassignment_role == "Daily supervisor" else "promotor"
            if reassignment_scope == "One student":
                target_option = "--student-email"
                selected_target_email = student_email.strip()
                if not selected_target_email:
                    raise ValueError(
                        "Enter the student's email in 'student_email' before running reassignment."
                    )
            else:
                target_option = "--departing-supervisor-email"
                selected_target_email = departing_researcher_email.strip()
                if not selected_target_email:
                    raise ValueError(
                        "Enter the departing researcher's email in "
                        "'departing_researcher_email' before running reassignment."
                    )
            inputs = identify_uploads(uploaded_paths, {"assignments", "researchers", "topics"})
            arguments = [
                "reassign", "--assignments", str(inputs["assignments"]),
                "--researchers", str(inputs["researchers"]), "--topics", str(inputs["topics"]),
                "--role", role, target_option, selected_target_email,
                "--output", str(output_directory / "final_assignments_reassigned.xlsx"),
                "--summary-output", str(output_directory / "supervisor_summary_reassigned.xlsx"),
                "--log-output", str(output_directory / "reassignment_log.csv"), *common_options,
            ]
            result_filename = "thesis_reassignment_results.zip"

        try:
            exit_code = run_command(arguments)
            if exit_code != 0:
                raise RuntimeError("The run stopped because an input or constraint was invalid. Read the message immediately above for the exact reason.")
        finally:
            shutil.rmtree(input_directory, ignore_errors=True)

        result_path = run_root / result_filename
        with zipfile.ZipFile(result_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(output_directory.iterdir()):
                archive.write(path, arcname=path.name)

        if task == "Complete allocation":
            report = json.loads((output_directory / "run_report.json").read_text(encoding="utf-8"))
            print(
                f"Completed: {report['assigned_students']} student(s), "
                f"including {report.get('carry_over_theses', report.get('carry_over_students', 0))} carry-over thesis group(s) "
                f"and {report.get('manual_review_theses', report.get('manual_review_students', 0))} manual-review group(s); "
                f"total preference cost {report['preference_cost']}."
            )
            for warning in report["warnings"]:
                print(f"Warning: {warning}")
        else:
            log = pd.read_csv(output_directory / "reassignment_log.csv")
            completed = log["new_supervisor_email"].fillna("").astype(str).str.strip().ne("")
            print(f"Completed: {int(completed.sum())} reassignment(s).")

        print(f"Downloading {result_filename}...")
        files.download(str(result_path))
        ''', cell_id='run', form=True),
        _markdown('''
        ## When finished

        Select **Runtime → Disconnect and delete runtime**. This removes the
        temporary Colab virtual machine, including generated result files.

        If the download did not start automatically, open the folder icon on the
        left, find the results ZIP under `thesis_allocation_run`, and download it.
        '''),
    ]
    return {
        "cells": cells,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"name": NOTEBOOK_PATH.name, "provenance": []},
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "thesis_allocation": {
                "generated_by": "scripts/build_colab_notebook.py",
                "package_source": "https://github.com/christofkoolen/computational-allocation-of-thesis-supervision",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def notebook_bytes() -> bytes:
    return (json.dumps(build_notebook(), indent=1, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail when the committed notebook is not up to date.")
    args = parser.parse_args()
    expected = notebook_bytes()
    if args.check:
        if not NOTEBOOK_PATH.is_file() or NOTEBOOK_PATH.read_bytes() != expected:
            print("The Colab notebook is stale. Run scripts/build_colab_notebook.py.", file=sys.stderr)
            return 1
        print("The Colab notebook is up to date.")
        return 0
    NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTEBOOK_PATH.write_bytes(expected)
    print(NOTEBOOK_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
