"""Shared helpers for fixture extraction scripts (tests/extract_*.py).

Maintainability review 1109, 段3: some 300 extraction scripts each carry their
own copy of these readers.  New extraction scripts import them from here; the
existing scripts are left as they are (they record how their fixtures were
made).  Each helper is the most common existing copy, named after it:

- ``lines``          -- extract_castle_top_floor_exit_fixture._lines (6 copies)
- ``rows``           -- extract_me_town_stops.rows (3 copies)
- ``decision_rows``  -- extract_town_approach_retired_fixture._decision_rows
- ``input_ends``     -- extract_town_approach_retired_fixture._input_ends (5 copies)
- ``sha``            -- extract_equip_tie_loop_fixture._sha256 (8 copies)
- ``write_xz``       -- the ``lzma.compress`` writes of the .xz fixtures

Usage from a script run as ``python tests/extract_<name>.py``::

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.support.extraction import decision_rows, input_ends, lines, sha, write_xz
"""

from __future__ import annotations

import gzip
import hashlib
import json
import lzma
from pathlib import Path

XZ_PRESET = 9 | lzma.PRESET_EXTREME


def _open_text(path: Path):
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def lines(path: Path) -> list[str]:
    """Every line of a (gzip or plain) UTF-8 text file, line endings kept."""
    with _open_text(path) as stream:
        return stream.read().splitlines(keepends=True)


def rows(path: Path) -> list[dict]:
    """The JSON object of every non-blank line of a (gzip or plain) JSONL file."""
    with _open_text(path) as stream:
        return [json.loads(line) for line in stream if line.strip()]


def decision_rows(path: Path) -> list[dict]:
    """The decision log rows (those carrying ``decision_sequence``) of a JSONL file."""
    return [row for row in rows(path) if "decision_sequence" in row]


def input_ends(decisions: list[dict], state_rows: list[dict]) -> list[int]:
    """The state row each decision read: walk back from the last row carrying the
    last decision's turn, stepping back by the recorded JSONL drain counts."""
    drains = [
        int(row.get("timing", {}).get("jsonl_drain_records") or 0)
        for row in decisions
    ]
    last = len(state_rows) - 1
    while state_rows[last].get("turn") != decisions[-1]["turn"]:
        last -= 1
    ends = [last]
    for index in range(len(decisions) - 1, 0, -1):
        end = max(0, ends[-1] - drains[index - 1])
        while end > 0 and state_rows[end].get("turn") != decisions[index - 1]["turn"]:
            end -= 1
        ends.append(end)
    ends.reverse()
    return ends


def sha(path: Path, *, normalize_newlines: bool = False) -> str:
    """SHA-256 of a file's bytes; ``normalize_newlines`` hashes CRLF as LF
    (the form the fixture pins compare against on a Windows checkout)."""
    data = Path(path).read_bytes()
    if normalize_newlines:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def write_xz(path: Path, payload, *, preset: int = XZ_PRESET) -> Path:
    """Write ``payload`` (bytes, str, or a JSON-serialisable value) xz-compressed.

    A str is encoded as UTF-8; any other non-bytes value is written as compact
    JSON (``ensure_ascii=False``).  Returns the path.
    """
    path = Path(path)
    if isinstance(payload, str):
        data = payload.encode("utf-8")
    elif isinstance(payload, (bytes, bytearray)):
        data = bytes(payload)
    else:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(lzma.compress(data, preset=preset))
    return path
