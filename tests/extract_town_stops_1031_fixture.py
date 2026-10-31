"""Freeze the recorded boards of the 2026-10-31 town-family stops (#47).

Sources: the viewing bots' captures copied to
``C:\\hengband-backups\\pdca\\captures\\latest-12h-1031`` (``<instance>/life-NNN/
captures/<stamp>-<kind>/state.jsonl.gz``, the game's output, UTF-8).  Every
frozen row is a verbatim line of that file, selected by its zero-based index;
each case keeps the line indices so the test can name its board.

Cases:
- ``town1``: n1-b life-276 ``20261031-084418-town-blocked-owner-retired-burst``.
  Lines 85 (``~f`` skill list), 95 and 113 (Home lists) and the decision boards
  105 (Home entrance, turn 1092301), 108 (Alchemist page, 1092564), 109
  (outside the Alchemist, 1092573), 112 and 114 (Home pages, 1092865) and 115
  (Home entrance, hungry, 1092876: recorded decision 12349, whose absorb was
  rewritten).  The duplicate frames 106, 107, 110, 111 carry no decision of
  their own (the decision rows of turns 1092301-1092865 are 12344-12348).
- ``town2``: n1-b life-276
  ``20261031-084905-town-blocked-shop-required-operation-uncomposable``.
  Lines 121 (arrival in town by recall, turn 1113555), 123 (``~f`` skill
  list), 124 and 126 (the town boards of decisions 2278 and 2279), 128 (the
  Alchemist entrance after the travel, turn 1113830) and the Alchemist pages
  129, 130 and 131 of decisions 2280-2282 (inscribe, sell, the stop).
- ``fuse``: the decision rows (``bot-decisions.jsonl.gz``) of n1-c life-057
  ``20261031-083408-loop-detected`` 3866-3895 and ``20261031-084544-loop-
  detected`` 704-733, both stopped by the runner's town-block fuse, trimmed to
  the reason, the key and the claim's id, goal kind and goal distance.

Only this tool reads the captures; the committed test reads the frozen file.
Usage: python tests/extract_town_stops_1031_fixture.py [captures directory]
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "town-stops-1031.json.gz"
DEFAULT_SOURCE = Path(r"C:\hengband-backups\pdca\captures\latest-12h-1031")
CASES = {
    "town1": (
        "n1-b/life-276/captures/20261031-084418-town-blocked-owner-retired-burst",
        (85, 95, 105, 108, 109, 112, 113, 114, 115),
    ),
    "town2": (
        "n1-b/life-276/captures/"
        "20261031-084905-town-blocked-shop-required-operation-uncomposable",
        (121, 123, 124, 126, 128, 129, 130, 131),
    ),
}

FUSE = {
    "walk": ("n1-c/life-057/captures/20261031-083408-loop-detected", 3866, 3895),
    "fight": ("n1-c/life-057/captures/20261031-084544-loop-detected", 704, 733),
}


def _fuse_rows(source: Path, relative: str, first: int, last: int) -> list[dict]:
    rows = {}
    path = source / relative / "bot-decisions.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            sequence = row.get("decision_sequence")
            if first <= (sequence or 0) <= last and sequence not in rows:
                claim = row.get("claim") or {}
                rows[sequence] = {
                    "decision_sequence": sequence,
                    "reason": row["reason"],
                    "key": row["key"],
                    "claim_id": claim.get("claim_id"),
                    "goal_kind": (claim.get("goal") or {}).get("kind"),
                    "distance": claim.get("distance"),
                }
    assert sorted(rows) == list(range(first, last + 1)), sorted(rows)
    return [rows[sequence] for sequence in range(first, last + 1)]


def _case(source: Path, relative: str, indices: tuple[int, ...]) -> dict:
    wanted = set(indices)
    rows = {}
    with gzip.open(source / relative / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            if index in wanted:
                rows[index] = json.loads(line)
    assert sorted(rows) == sorted(wanted), sorted(wanted - set(rows))
    return {"source": relative, "rows": [[index, rows[index]] for index in indices]}


def main(source: Path) -> None:
    document = {name: _case(source, *spec) for name, spec in CASES.items()}
    town2 = dict(document["town2"]["rows"])
    assert [town2[index]["store"]["store_type"] for index in (129, 130, 131)] == [4, 4, 4]
    document["fuse"] = {name: _fuse_rows(source, *spec) for name, spec in FUSE.items()}
    assert document["fuse"]["walk"][0]["reason"].startswith("town:blocked:")
    assert document["fuse"]["fight"][0]["reason"].startswith("town:blocked:")
    town1 = dict(document["town1"]["rows"])
    assert town1[115]["turn"] == 1092876 and not town1[115].get("store")
    assert (town1[115]["player"]["y"], town1[115]["player"]["x"]) == (45, 123)
    OUT.write_bytes(gzip.compress(
        json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8"), mtime=0))
    print(OUT.name, hashlib.sha256(OUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE)
