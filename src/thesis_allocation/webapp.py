"""Local-first Streamlit interface for non-programmer users."""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pandas as pd
import streamlit as st

from thesis_allocation.errors import ThesisAllocationError
from thesis_allocation.matching import ROLE_SPECS, match_supervisors
from thesis_allocation.replacement import reassign_supervision
from thesis_allocation.schema import (
    normalize_assignments,
    normalize_researchers,
)
from thesis_allocation.scraping import enrich_researchers
from thesis_allocation.similarity import (
    DEFAULT_EMBEDDING_MODEL,
    SimilarityBackend,
    create_similarity_backend,
)
from thesis_allocation.templates import TEMPLATE_COLUMNS
from thesis_allocation.topics import allocate_topics


@dataclass(frozen=True)
class PipelineAppResult:
    """Complete pipeline output prepared for browser display and download."""

    researchers: pd.DataFrame
    topic_assignments: pd.DataFrame
    final_assignments: pd.DataFrame
    supervisor_summary: pd.DataFrame
    preference_cost: int
    assigned_students: int
    warnings: tuple[str, ...]

    def download_bundle(self) -> bytes:
        report = {
            "assigned_students": self.assigned_students,
            "preference_cost": self.preference_cost,
            "warnings": list(self.warnings),
        }
        return files_to_zip_bytes(
            {
                "researchers_enriched.xlsx": dataframe_to_excel_bytes(
                    self.researchers
                ),
                "topic_assignments.xlsx": dataframe_to_excel_bytes(
                    self.topic_assignments
                ),
                "final_assignments.xlsx": dataframe_to_excel_bytes(
                    self.final_assignments
                ),
                "supervisor_summary.xlsx": dataframe_to_excel_bytes(
                    self.supervisor_summary
                ),
                "run_report.json": (
                    json.dumps(report, indent=2, ensure_ascii=False) + "\n"
                ).encode("utf-8"),
            }
        )


@dataclass(frozen=True)
class ReassignmentAppResult:
    """Targeted reassignment output prepared for download."""

    assignments: pd.DataFrame
    summary: pd.DataFrame
    log: pd.DataFrame
    warnings: tuple[str, ...]

    def download_bundle(self) -> bytes:
        return files_to_zip_bytes(
            {
                "final_assignments_reassigned.xlsx": dataframe_to_excel_bytes(
                    self.assignments
                ),
                "supervisor_summary_reassigned.xlsx": dataframe_to_excel_bytes(
                    self.summary
                ),
                "reassignment_log.csv": self.log.to_csv(index=False).encode("utf-8"),
            }
        )


def dataframe_to_excel_bytes(frame: pd.DataFrame) -> bytes:
    """Serialize one DataFrame to an in-memory Excel workbook."""

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False)
    return buffer.getvalue()


def files_to_zip_bytes(files: dict[str, bytes]) -> bytes:
    """Create a deterministic in-memory ZIP archive."""

    buffer = BytesIO()
    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for filename in sorted(files):
            entry = zipfile.ZipInfo(
                filename=filename,
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, files[filename])
    return buffer.getvalue()


def template_zip_bytes() -> bytes:
    """Return the three canonical input templates as one ZIP download."""

    files = {
        filename: dataframe_to_excel_bytes(pd.DataFrame(columns=columns))
        for filename, columns in TEMPLATE_COLUMNS.items()
    }
    return files_to_zip_bytes(files)


def read_uploaded_table(upload: BinaryIO) -> pd.DataFrame:
    """Read an uploaded XLSX, CSV, or TSV file without writing it to disk."""

    filename = getattr(upload, "name", "")
    suffix = Path(filename).suffix.casefold()
    upload.seek(0)
    if suffix == ".xlsx":
        return pd.read_excel(upload)
    if suffix == ".csv":
        return pd.read_csv(upload)
    if suffix == ".tsv":
        return pd.read_csv(upload, sep="\t")
    raise ThesisAllocationError(
        f"Unsupported file '{filename}'. Upload an .xlsx, .csv, or .tsv file."
    )


def run_pipeline_frames(
    researchers: pd.DataFrame,
    topics: pd.DataFrame,
    preferences: pd.DataFrame,
    backend: SimilarityBackend,
    *,
    retrieve_profile_text: bool,
    refresh_profile_text: bool,
    request_delay_seconds: float,
    duplicate_policy: str,
    allow_partial: bool,
    enforce_distinct_roles: bool,
) -> PipelineAppResult:
    """Run the complete pipeline from in-memory browser uploads."""

    if retrieve_profile_text:
        scrape_result = enrich_researchers(
            researchers,
            refresh=refresh_profile_text,
            delay_seconds=request_delay_seconds,
        )
        researcher_table = scrape_result.researchers
        scrape_warnings = scrape_result.warnings
    else:
        researcher_table = normalize_researchers(researchers)
        scrape_warnings = ()

    topic_result = allocate_topics(
        preferences,
        topics,
        duplicate_policy=duplicate_policy,
        allow_partial=allow_partial,
    )
    match_result = match_supervisors(
        topic_result.assignments,
        researcher_table,
        topics,
        backend,
        allow_partial=allow_partial,
        enforce_distinct_roles=enforce_distinct_roles,
    )
    warnings = tuple(
        dict.fromkeys(
            [
                *scrape_warnings,
                *topic_result.warnings,
                *match_result.warnings,
            ]
        )
    )
    return PipelineAppResult(
        researchers=researcher_table,
        topic_assignments=topic_result.assignments,
        final_assignments=match_result.assignments,
        supervisor_summary=match_result.summary,
        preference_cost=topic_result.total_cost,
        assigned_students=topic_result.assigned_count,
        warnings=warnings,
    )


def run_reassignment_frames(
    assignments: pd.DataFrame,
    researchers: pd.DataFrame,
    topics: pd.DataFrame,
    backend: SimilarityBackend,
    *,
    role: str,
    student_email: str | None,
    departing_supervisor_email: str | None,
    allow_partial: bool,
    enforce_distinct_roles: bool,
) -> ReassignmentAppResult:
    """Run one targeted reassignment operation from uploaded tables."""

    result = reassign_supervision(
        assignments,
        researchers,
        topics,
        backend,
        role=role,
        student_email=student_email,
        departing_supervisor_email=departing_supervisor_email,
        allow_partial=allow_partial,
        enforce_distinct_roles=enforce_distinct_roles,
    )
    return ReassignmentAppResult(
        assignments=result.assignments,
        summary=result.summary,
        log=result.log,
        warnings=result.warnings,
    )


@st.cache_resource(show_spinner=False)
def _cached_backend(name: str, model_name: str) -> SimilarityBackend:
    return create_similarity_backend(name, model_name=model_name)


def _show_warnings(warnings: tuple[str, ...]) -> None:
    if not warnings:
        return
    with st.expander(f"Warnings ({len(warnings)})", expanded=True):
        for warning in warnings:
            st.warning(warning)


def _backend_controls(key_prefix: str) -> tuple[str, str]:
    backend_label = st.selectbox(
        "Matching method",
        ("Semantic matching", "Offline TF-IDF fallback"),
        key=f"{key_prefix}_backend",
        help=(
            "Semantic matching gives the intended result. TF-IDF is useful for "
            "offline testing and does not understand meaning beyond shared words."
        ),
    )
    backend = (
        "sentence-transformers"
        if backend_label == "Semantic matching"
        else "tfidf"
    )
    model = st.text_input(
        "Semantic model",
        value=DEFAULT_EMBEDDING_MODEL,
        disabled=backend != "sentence-transformers",
        key=f"{key_prefix}_model",
    )
    return backend, model


def _render_templates() -> None:
    st.header("Input templates")
    st.write(
        "Download these blank Excel workbooks, fill one row per researcher, "
        "topic, or student, and return to **Run complete allocation**."
    )
    st.download_button(
        "Download the three Excel templates",
        data=template_zip_bytes(),
        file_name="thesis_allocation_input_templates.zip",
        mime="application/zip",
        type="primary",
    )

    for filename, columns in TEMPLATE_COLUMNS.items():
        with st.expander(filename):
            st.code("\n".join(columns), language=None)


def _render_pipeline() -> None:
    st.header("Run complete allocation")
    st.write(
        "Upload the three completed input files. The app validates them before "
        "allocating topics or supervisors."
    )

    with st.form("pipeline_form"):
        first, second, third = st.columns(3)
        with first:
            researcher_upload = st.file_uploader(
                "1. Researchers",
                type=("xlsx", "csv", "tsv"),
                key="pipeline_researchers",
            )
        with second:
            topic_upload = st.file_uploader(
                "2. Thesis topics",
                type=("xlsx", "csv", "tsv"),
                key="pipeline_topics",
            )
        with third:
            preference_upload = st.file_uploader(
                "3. Student preferences",
                type=("xlsx", "csv", "tsv"),
                key="pipeline_preferences",
            )

        with st.expander("Options"):
            retrieve_profile_text = st.checkbox(
                "Retrieve missing profile and publication text from URLs",
                value=True,
            )
            refresh_profile_text = st.checkbox(
                "Replace profile text that is already present",
                value=False,
                disabled=not retrieve_profile_text,
            )
            request_delay = st.slider(
                "Delay between web requests (seconds)",
                min_value=0.0,
                max_value=2.0,
                value=0.5,
                step=0.1,
                disabled=not retrieve_profile_text,
            )
            duplicate_policy_label = st.selectbox(
                "Duplicate student submissions",
                (
                    "Keep the latest row",
                    "Keep the first row",
                    "Stop and report duplicates",
                ),
            )
            allow_partial = st.checkbox(
                "Allow partial results when a complete allocation is impossible",
                value=False,
            )
            allow_same_person = st.checkbox(
                "Allow the same person as daily supervisor and promotor",
                value=False,
            )
            backend_name, model_name = _backend_controls("pipeline")

        submitted = st.form_submit_button(
            "Run allocation",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        st.session_state.pop("pipeline_app_result", None)
        if not all((researcher_upload, topic_upload, preference_upload)):
            st.error("Upload all three input files before running the allocation.")
        else:
            duplicate_policy = {
                "Keep the latest row": "keep-last",
                "Keep the first row": "keep-first",
                "Stop and report duplicates": "error",
            }[duplicate_policy_label]
            try:
                with st.spinner(
                    "Running validation, topic allocation, and supervisor matching..."
                ):
                    backend = _cached_backend(backend_name, model_name)
                    result = run_pipeline_frames(
                        read_uploaded_table(researcher_upload),
                        read_uploaded_table(topic_upload),
                        read_uploaded_table(preference_upload),
                        backend,
                        retrieve_profile_text=retrieve_profile_text,
                        refresh_profile_text=refresh_profile_text,
                        request_delay_seconds=request_delay,
                        duplicate_policy=duplicate_policy,
                        allow_partial=allow_partial,
                        enforce_distinct_roles=not allow_same_person,
                    )
                st.session_state["pipeline_app_result"] = result
            except ThesisAllocationError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Unexpected error: {exc}")

    result = st.session_state.get("pipeline_app_result")
    if not isinstance(result, PipelineAppResult):
        return

    st.success("Allocation completed.")
    first, second = st.columns(2)
    first.metric("Students assigned", result.assigned_students)
    second.metric("Total preference cost", result.preference_cost)
    _show_warnings(result.warnings)
    st.download_button(
        "Download all results",
        data=result.download_bundle(),
        file_name="thesis_allocation_results.zip",
        mime="application/zip",
        type="primary",
    )
    with st.expander("Preview final assignments", expanded=True):
        st.dataframe(result.final_assignments, use_container_width=True)
    with st.expander("Preview supervisor workload"):
        st.dataframe(result.supervisor_summary, use_container_width=True)


def _format_person_option(
    email: str,
    names_by_email: dict[str, str],
) -> str:
    name = names_by_email.get(email, "")
    return f"{name} ({email})" if name else email


def _render_reassignment() -> None:
    st.header("Reassign supervision")
    st.write(
        "Upload the previous results and select either one student or a "
        "departing supervisor. Every unrelated assignment remains fixed."
    )

    first, second, third = st.columns(3)
    with first:
        assignment_upload = st.file_uploader(
            "Final assignments",
            type=("xlsx", "csv", "tsv"),
            key="reassign_assignments",
        )
    with second:
        researcher_upload = st.file_uploader(
            "Researchers",
            type=("xlsx", "csv", "tsv"),
            key="reassign_researchers",
        )
    with third:
        topic_upload = st.file_uploader(
            "Thesis topics",
            type=("xlsx", "csv", "tsv"),
            key="reassign_topics",
        )

    role_label = st.selectbox(
        "Role to replace",
        ("Daily supervisor", "Promotor"),
    )
    role = "daily_supervisor" if role_label == "Daily supervisor" else "promotor"
    target_mode = st.radio(
        "Replacement scope",
        ("One student", "Everyone assigned to a departing supervisor"),
        horizontal=True,
    )

    canonical_assignments: pd.DataFrame | None = None
    if assignment_upload is not None:
        try:
            canonical_assignments = normalize_assignments(
                read_uploaded_table(assignment_upload)
            )
        except ThesisAllocationError as exc:
            st.error(str(exc))

    target_value: str | None = None
    if canonical_assignments is not None:
        names_by_email = dict(
            zip(
                canonical_assignments["email"],
                canonical_assignments["full_name"],
                strict=False,
            )
        )
        if target_mode == "One student":
            options = sorted(canonical_assignments["email"].unique())
            target_value = st.selectbox(
                "Student",
                options,
                format_func=lambda email: _format_person_option(
                    email,
                    names_by_email,
                ),
            )
        else:
            spec = ROLE_SPECS[role]
            supervisor_names = dict(
                zip(
                    canonical_assignments[spec.email_column],
                    canonical_assignments[spec.name_column],
                    strict=False,
                )
            )
            options = sorted(
                {
                    email
                    for email in canonical_assignments[spec.email_column]
                    if email
                }
            )
            if options:
                target_value = st.selectbox(
                    "Departing supervisor",
                    options,
                    format_func=lambda email: _format_person_option(
                        email,
                        supervisor_names,
                    ),
                )
            else:
                st.warning(f"No existing {role_label.casefold()} values were found.")

    with st.expander("Options"):
        allow_partial = st.checkbox(
            "Allow partial replacements when capacity is insufficient",
            value=False,
            key="reassign_partial",
        )
        allow_same_person = st.checkbox(
            "Allow the same person as daily supervisor and promotor",
            value=False,
            key="reassign_same_person",
        )
        backend_name, model_name = _backend_controls("reassignment")

    submitted = st.button(
        "Run reassignment",
        type="primary",
        disabled=not all(
            (
                assignment_upload,
                researcher_upload,
                topic_upload,
                target_value,
            )
        ),
    )
    if submitted:
        st.session_state.pop("reassignment_app_result", None)
        try:
            with st.spinner("Recomputing only the selected supervision role..."):
                backend = _cached_backend(backend_name, model_name)
                result = run_reassignment_frames(
                    read_uploaded_table(assignment_upload),
                    read_uploaded_table(researcher_upload),
                    read_uploaded_table(topic_upload),
                    backend,
                    role=role,
                    student_email=(
                        target_value if target_mode == "One student" else None
                    ),
                    departing_supervisor_email=(
                        target_value
                        if target_mode
                        == "Everyone assigned to a departing supervisor"
                        else None
                    ),
                    allow_partial=allow_partial,
                    enforce_distinct_roles=not allow_same_person,
                )
            st.session_state["reassignment_app_result"] = result
        except ThesisAllocationError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Unexpected error: {exc}")

    result = st.session_state.get("reassignment_app_result")
    if not isinstance(result, ReassignmentAppResult):
        return

    st.success(f"Reassigned {len(result.log)} supervision record(s).")
    _show_warnings(result.warnings)
    st.download_button(
        "Download reassignment results",
        data=result.download_bundle(),
        file_name="thesis_reassignment_results.zip",
        mime="application/zip",
        type="primary",
    )
    st.dataframe(result.log, use_container_width=True)


def main() -> None:
    """Render the Streamlit application."""

    st.set_page_config(
        page_title="Thesis Allocation",
        page_icon="🎓",
        layout="wide",
    )
    st.title("Thesis allocation and supervision")
    st.caption(
        "A guided interface for researcher enrichment, topic allocation, "
        "supervisor matching, and targeted reassignment."
    )
    st.info(
        "When launched with START_APP.bat, uploaded student data is processed "
        "on this computer and the app listens only on localhost. Enabling "
        "profile retrieval sends requests to the profile URLs in the researcher file."
    )

    page = st.sidebar.radio(
        "Choose a task",
        (
            "Run complete allocation",
            "Reassign supervision",
            "Input templates",
        ),
    )
    if page == "Run complete allocation":
        _render_pipeline()
    elif page == "Reassign supervision":
        _render_reassignment()
    else:
        _render_templates()


if __name__ == "__main__":
    main()
