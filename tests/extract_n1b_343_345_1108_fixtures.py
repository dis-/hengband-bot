"""Freeze the n1-b life-343 and life-345 stops (2026-11-08).

Source: the viewing bot's ~/hengbot-soak/n1-b/<life>/incident-captures (copied with
their town-arrival checkpoints; pass the directory holding life-343/ and life-345/).

* light (life-343, 04:54): the arrival checkpoint of 20261108-045459-town-blocked-owner-
  retired-burst (the restart in Angwil with the lantern out) and its journal rows 0..12:
  the walks to the Magic shop and the staff sequence's inn travel from its lit entrance.
* zul (life-345, 08:13): the arrival checkpoint of 20261108-081359-town-blocked-owner-
  retired-burst (the restart in Zul at (64,1) after the ambush recall), its journal, and
  the boards of 20261108-081348-quest-blocked-me-staff snapshots-current at turns 1744015
  (the Outpost after the recall, the Ring of Levitation worn over the sub ring and the
  Ring of Lightning [+10] in the pack), 1772427 (the third Zul entry, the trip under way)
  and 1772550 (the ambush board and its refused '<').
Only this tool reads the capture.

    python tests/extract_n1b_343_345_1108_fixtures.py <captures-root>
"""

from __future__ import annotations

import gzip
import io
import json
from pathlib import Path
import sys
import tarfile

FIXTURES = Path(__file__).with_name("fixtures") / "n1b-343-345-1108"
LIGHT = "life-343/incident-captures/20261108-045459-town-blocked-owner-retired-burst"
ZUL = "life-345/incident-captures/20261108-081359-town-blocked-owner-retired-burst"
ZUL_RING = "life-345/incident-captures/20261108-081348-quest-blocked-me-staff"
LIGHT_ROWS = 13
ZUL_TURNS = (1744015, 1772427, 1772550)


def _add(tar, name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def _checkpoint(path: Path, capture: Path, rows: int | None, extra=()) -> None:
    visit = capture / "town-arrival"
    with tarfile.open(path, "w:xz") as tar:
        _add(tar, "policy.pkl", (visit / "policy.pkl").read_bytes())
        _add(tar, "sidecars.json", (visit / "sidecars.json").read_bytes())
        for item in sorted((visit / "sidecars").iterdir()):
            _add(tar, f"sidecars/{item.name}", item.read_bytes())
        with gzip.open(visit / "journal.jsonl.gz", "rt", encoding="utf-8") as stream:
            kept = [line for index, line in enumerate(stream) if rows is None or index < rows]
        _add(tar, "journal.jsonl.gz", gzip.compress("".join(kept).encode("utf-8"), mtime=0))
        for name, data in extra:
            _add(tar, name, data)


def _boards(capture: Path) -> bytes:
    """The recorded player_turn boards of ZUL_TURNS, in ring order."""
    kept = []
    path = capture / "snapshots" / "snapshots-current.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("type") == "player_turn" and row.get("turn") in ZUL_TURNS:
                kept.append(line if line.endswith("\n") else line + "\n")
    return gzip.compress("".join(kept).encode("utf-8"), mtime=0)


def main(root: Path) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    _checkpoint(FIXTURES / "light.tar.xz", root / LIGHT, LIGHT_ROWS)
    _checkpoint(FIXTURES / "zul.tar.xz", root / ZUL, None,
                extra=(("boards.jsonl.gz", _boards(root / ZUL_RING)),))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
