"""Domain-specific exceptions with user-facing messages."""

from __future__ import annotations

from collections.abc import Iterable


class ThesisAllocationError(Exception):
    """Base class for expected pipeline errors."""


class InputValidationError(ThesisAllocationError):
    """Raised when an input table does not satisfy its data contract."""

    def __init__(self, issues: str | Iterable[str]):
        if isinstance(issues, str):
            normalized = [issues]
        else:
            normalized = [str(issue) for issue in issues]
        self.issues = tuple(issue for issue in normalized if issue)
        message = "Input validation failed"
        if self.issues:
            message += ":\n" + "\n".join(f"  - {issue}" for issue in self.issues)
        super().__init__(message)


class InfeasibleAssignmentError(ThesisAllocationError):
    """Raised when the requested constraints cannot yield a full assignment."""

