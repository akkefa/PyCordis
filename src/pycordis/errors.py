"""Stable runtime error codes."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


class CordisError(RuntimeError):
    """Runtime misuse with a machine-readable code."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True)
class ValidationIssue:
    """One diagnostic with a copied field/index path."""

    message: str
    path: tuple[str | int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.message, str):
            raise TypeError("validation issue message must be a string")
        if isinstance(self.path, (str, bytes)):
            raise TypeError("validation issue path must be a sequence of field names or indices")
        path = tuple(self.path)
        if any(not isinstance(part, (str, int)) or isinstance(part, bool) for part in path):
            raise TypeError("validation issue path must contain field names or indices")
        object.__setattr__(self, "path", path)


class ValidationError(TypeError):
    """Structured schema failure; adapters may raise this from validate()."""

    def __init__(self, issues: Iterable[ValidationIssue]) -> None:
        self._issues = tuple(issues)
        if not self._issues or any(
            not isinstance(issue, ValidationIssue) for issue in self._issues
        ):
            raise TypeError("ValidationError requires one or more ValidationIssue objects")
        lines = []
        for issue in self._issues:
            suffix = f" (at {'.'.join(map(str, issue.path))})" if issue.path else ""
            lines.append(f"  - {issue.message}{suffix}")
        super().__init__("invalid config:\n" + "\n".join(lines))

    @property
    def issues(self) -> tuple[ValidationIssue, ...]:
        return self._issues
