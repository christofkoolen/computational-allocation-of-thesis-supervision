"""Command-line interface for each stage and the complete pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from thesis_allocation.errors import ThesisAllocationError
from thesis_allocation.io import read_table, write_table
from thesis_allocation.matching import match_supervisors
from thesis_allocation.replacement import reassign_supervision
from thesis_allocation.schema import normalize_researchers
from thesis_allocation.scraping import enrich_researchers
from thesis_allocation.similarity import (
    DEFAULT_EMBEDDING_MODEL,
    create_similarity_backend,
)
from thesis_allocation.templates import create_templates
from thesis_allocation.topics import allocate_topics


def _add_backend_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--backend",
        choices=("sentence-transformers", "tfidf"),
        default="sentence-transformers",
        help="Similarity backend. tfidf is an offline lexical fallback.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_EMBEDDING_MODEL,
        help="Sentence-transformers model name.",
    )


def _add_matching_arguments(parser: argparse.ArgumentParser) -> None:
    _add_backend_arguments(parser)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Write partial results instead of failing on insufficient capacity.",
    )
    parser.add_argument(
        "--allow-same-person",
        action="store_true",
        help="Allow one researcher to be both roles for the same student.",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the complete CLI parser."""

    parser = argparse.ArgumentParser(
        prog="thesis-allocation",
        description="Allocate thesis topics and match supervision roles.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    templates_parser = subparsers.add_parser(
        "create-templates",
        help="Create blank canonical input workbooks.",
    )
    templates_parser.add_argument("output_directory")
    templates_parser.add_argument("--force", action="store_true")

    scrape_parser = subparsers.add_parser(
        "scrape-researchers",
        help="Enrich researcher rows with profile and publication text.",
    )
    scrape_parser.add_argument("--researchers", required=True)
    scrape_parser.add_argument("--output", required=True)
    scrape_parser.add_argument("--refresh", action="store_true")
    scrape_parser.add_argument("--timeout", type=float, default=20.0)
    scrape_parser.add_argument("--delay", type=float, default=0.5)

    allocate_parser = subparsers.add_parser(
        "allocate-topics",
        help="Minimize total ranked-preference cost under topic capacities.",
    )
    allocate_parser.add_argument("--preferences", required=True)
    allocate_parser.add_argument("--topics", required=True)
    allocate_parser.add_argument("--output", required=True)
    allocate_parser.add_argument(
        "--duplicate-policy",
        choices=("error", "keep-first", "keep-last"),
        default="keep-last",
    )
    allocate_parser.add_argument("--allow-partial", action="store_true")
    allocate_parser.add_argument("--fuzzy-threshold", type=float, default=0.90)
    allocate_parser.add_argument("--fuzzy-margin", type=float, default=0.05)

    match_parser = subparsers.add_parser(
        "match-supervisors",
        help="Semantically match daily supervisors and promotors.",
    )
    match_parser.add_argument("--assignments", required=True)
    match_parser.add_argument("--topics", required=True)
    match_parser.add_argument("--researchers", required=True)
    match_parser.add_argument("--output", required=True)
    match_parser.add_argument("--summary-output", required=True)
    _add_matching_arguments(match_parser)

    run_parser = subparsers.add_parser(
        "run",
        help="Run scraping, topic allocation, and supervisor matching.",
    )
    run_parser.add_argument("--researchers", required=True)
    run_parser.add_argument("--topics", required=True)
    run_parser.add_argument("--preferences", required=True)
    run_parser.add_argument("--output-directory", required=True)
    run_parser.add_argument("--skip-scrape", action="store_true")
    run_parser.add_argument("--refresh-scrape", action="store_true")
    run_parser.add_argument("--timeout", type=float, default=20.0)
    run_parser.add_argument("--delay", type=float, default=0.5)
    run_parser.add_argument(
        "--duplicate-policy",
        choices=("error", "keep-first", "keep-last"),
        default="keep-last",
    )
    run_parser.add_argument("--fuzzy-threshold", type=float, default=0.90)
    run_parser.add_argument("--fuzzy-margin", type=float, default=0.05)
    _add_matching_arguments(run_parser)

    reassign_parser = subparsers.add_parser(
        "reassign",
        help="Replace one assignment or all work held by a departing supervisor.",
    )
    reassign_parser.add_argument("--assignments", required=True)
    reassign_parser.add_argument("--topics", required=True)
    reassign_parser.add_argument("--researchers", required=True)
    reassign_parser.add_argument("--output", required=True)
    reassign_parser.add_argument("--summary-output", required=True)
    reassign_parser.add_argument("--log-output", required=True)
    reassign_parser.add_argument(
        "--role",
        required=True,
        choices=("daily_supervisor", "promotor"),
    )
    target_group = reassign_parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--student-email")
    target_group.add_argument("--departing-supervisor-email")
    _add_matching_arguments(reassign_parser)

    return parser


def _print_warnings(warnings: tuple[str, ...]) -> None:
    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)


def _command_create_templates(args: argparse.Namespace) -> None:
    paths = create_templates(args.output_directory, force=args.force)
    for path in paths:
        print(path)


def _command_scrape(args: argparse.Namespace) -> None:
    result = enrich_researchers(
        read_table(args.researchers),
        refresh=args.refresh,
        timeout=args.timeout,
        delay_seconds=args.delay,
    )
    path = write_table(result.researchers, args.output)
    _print_warnings(result.warnings)
    print(path)


def _command_allocate(args: argparse.Namespace) -> None:
    result = allocate_topics(
        read_table(args.preferences),
        read_table(args.topics),
        duplicate_policy=args.duplicate_policy,
        allow_partial=args.allow_partial,
        fuzzy_threshold=args.fuzzy_threshold,
        fuzzy_margin=args.fuzzy_margin,
    )
    path = write_table(result.assignments, args.output)
    _print_warnings(result.warnings)
    print(
        f"{path}: assigned {result.assigned_count} student(s), "
        f"total preference cost {result.total_cost}"
    )


def _command_match(args: argparse.Namespace) -> None:
    backend = create_similarity_backend(args.backend, model_name=args.model)
    result = match_supervisors(
        read_table(args.assignments),
        read_table(args.researchers),
        read_table(args.topics),
        backend,
        allow_partial=args.allow_partial,
        enforce_distinct_roles=not args.allow_same_person,
    )
    assignment_path = write_table(result.assignments, args.output)
    summary_path = write_table(result.summary, args.summary_output)
    _print_warnings(result.warnings)
    print(assignment_path)
    print(summary_path)


def _command_run(args: argparse.Namespace) -> None:
    output_directory = Path(args.output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)

    raw_researchers = read_table(args.researchers)
    if args.skip_scrape:
        researcher_table = normalize_researchers(raw_researchers)
        scrape_warnings: tuple[str, ...] = ()
    else:
        scrape_result = enrich_researchers(
            raw_researchers,
            refresh=args.refresh_scrape,
            timeout=args.timeout,
            delay_seconds=args.delay,
        )
        researcher_table = scrape_result.researchers
        scrape_warnings = scrape_result.warnings
    researchers_path = write_table(
        researcher_table,
        output_directory / "researchers_enriched.xlsx",
    )

    topic_table = read_table(args.topics)
    allocation = allocate_topics(
        read_table(args.preferences),
        topic_table,
        duplicate_policy=args.duplicate_policy,
        allow_partial=args.allow_partial,
        fuzzy_threshold=args.fuzzy_threshold,
        fuzzy_margin=args.fuzzy_margin,
    )
    topics_path = write_table(
        allocation.assignments,
        output_directory / "topic_assignments.xlsx",
    )

    backend = create_similarity_backend(args.backend, model_name=args.model)
    matching = match_supervisors(
        allocation.assignments,
        researcher_table,
        topic_table,
        backend,
        allow_partial=args.allow_partial,
        enforce_distinct_roles=not args.allow_same_person,
    )
    final_path = write_table(
        matching.assignments,
        output_directory / "final_assignments.xlsx",
    )
    summary_path = write_table(
        matching.summary,
        output_directory / "supervisor_summary.xlsx",
    )

    warnings = tuple(
        dict.fromkeys(
            [
                *scrape_warnings,
                *allocation.warnings,
                *matching.warnings,
            ]
        )
    )
    report = {
        "assigned_students": allocation.assigned_count,
        "preference_cost": allocation.total_cost,
        "warnings": list(warnings),
        "outputs": {
            "researchers": str(researchers_path),
            "topic_assignments": str(topics_path),
            "final_assignments": str(final_path),
            "supervisor_summary": str(summary_path),
        },
    }
    report_path = output_directory / "run_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _print_warnings(warnings)
    for path in (researchers_path, topics_path, final_path, summary_path, report_path):
        print(path)


def _command_reassign(args: argparse.Namespace) -> None:
    backend = create_similarity_backend(args.backend, model_name=args.model)
    result = reassign_supervision(
        read_table(args.assignments),
        read_table(args.researchers),
        read_table(args.topics),
        backend,
        role=args.role,
        student_email=args.student_email,
        departing_supervisor_email=args.departing_supervisor_email,
        allow_partial=args.allow_partial,
        enforce_distinct_roles=not args.allow_same_person,
    )
    assignment_path = write_table(result.assignments, args.output)
    summary_path = write_table(result.summary, args.summary_output)
    log_path = write_table(result.log, args.log_output)
    _print_warnings(result.warnings)
    print(assignment_path)
    print(summary_path)
    print(log_path)


COMMANDS = {
    "create-templates": _command_create_templates,
    "scrape-researchers": _command_scrape,
    "allocate-topics": _command_allocate,
    "match-supervisors": _command_match,
    "run": _command_run,
    "reassign": _command_reassign,
}


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit status."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        COMMANDS[args.command](args)
    except ThesisAllocationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0

