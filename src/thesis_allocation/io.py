"""Tabular file input and output."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from thesis_allocation.errors import InputValidationError


SUPPORTED_SUFFIXES = {".csv", ".tsv", ".xls", ".xlsx"}


def read_table(path: str | Path, *, sheet_name: str | int = 0) -> pd.DataFrame:
    """Read an Excel, CSV, or TSV table."""

    resolved = Path(path)
    if not resolved.is_file():
        raise InputValidationError(f"Input file does not exist: {resolved}")
    suffix = resolved.suffix.casefold()
    if suffix not in SUPPORTED_SUFFIXES:
        raise InputValidationError(
            f"Unsupported input format '{suffix}' for {resolved}; "
            f"use one of {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )
    if suffix in {".xls", ".xlsx"}:
        return pd.read_excel(resolved, sheet_name=sheet_name)
    separator = "\t" if suffix == ".tsv" else ","
    return pd.read_csv(resolved, sep=separator)


def write_table(frame: pd.DataFrame, path: str | Path) -> Path:
    """Write a table based on the output filename extension."""

    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    suffix = resolved.suffix.casefold()
    if suffix == ".xlsx":
        frame.to_excel(resolved, index=False)
    elif suffix == ".csv":
        frame.to_csv(resolved, index=False)
    elif suffix == ".tsv":
        frame.to_csv(resolved, sep="\t", index=False)
    else:
        raise InputValidationError(
            f"Unsupported output format '{suffix}' for {resolved}; "
            "use .xlsx, .csv, or .tsv"
        )
    return resolved


def write_workbook(sheets: dict[str, pd.DataFrame], path: str | Path) -> Path:
    """Write several tables to one Excel workbook."""

    resolved = Path(path)
    if resolved.suffix.casefold() != ".xlsx":
        raise InputValidationError("Multi-sheet output must use an .xlsx filename")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(resolved, engine="openpyxl") as writer:
        for sheet_name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return resolved
