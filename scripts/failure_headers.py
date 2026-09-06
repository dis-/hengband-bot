"""Shared parsing for unittest FAIL/ERROR headers, including subTests."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterator


@dataclass(frozen=True)
class FailureHeader:
    kind: str
    name: str
    identity: str
    start: int
    end: int


def failure_identity_pattern(*, test_names_only: bool) -> re.Pattern[str]:
    """Return the legacy one-capture regex backed by the shared grammar."""
    name = r"test\S+" if test_names_only else r"\S+"
    return re.compile(
        rf"^(?:FAIL|ERROR): {name} \(([^)\r\n]+)\)"
        r"(?: \[[^\r\n]*\])?(?: \([^\r\n]*\))?$",
        re.MULTILINE,
    )


def iter_failure_headers(text: str, *, test_names_only: bool) -> Iterator[FailureHeader]:
    r"""Yield headers; ``test_names_only`` selects ``test\S+`` versus ``\S+``.

    The gates accept only normal unittest test names.  The receipt and mutation
    summaries deliberately accept any non-whitespace display name because their
    job is to record runner output, including synthetic or custom test runners.
    """
    name = r"test\S+" if test_names_only else r"\S+"
    pattern = re.compile(
        rf"^(FAIL|ERROR): ({name}) \(([^)\r\n]+)\)"
        r"(?: \[[^\r\n]*\])?(?: \([^\r\n]*\))?$",
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        yield FailureHeader(match.group(1), match.group(2), match.group(3),
                            match.start(), match.end())


def failure_sections(text: str, *, test_names_only: bool) -> dict[str, str]:
    """Return all failure sections per identity, preserving repeated subTests."""
    headers = list(iter_failure_headers(text, test_names_only=test_names_only))
    sections: dict[str, list[str]] = {}
    for index, header in enumerate(headers):
        end = headers[index + 1].start if index + 1 < len(headers) else len(text)
        sections.setdefault(header.identity, []).append(text[header.start:end])
    return {identity: "\n".join(parts) for identity, parts in sections.items()}
