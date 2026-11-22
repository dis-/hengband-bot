"""Extract tests/fixtures/n1c-220-flipflops-1122/{feet,sub_ring,body}/.

n1-c life-220 (Magic-Eater Lv21-23, build bot-cc0ba74d6 / bot-af35fa0d9) stopped three times in
town on 2026-11-22 with the equipment round trip (equipment_visit_journal):

* 06:53:42 ``town:blocked:equipment-slot-flipflop:feet``,
* 07:23:21 ``town:blocked:equipment-slot-flipflop:sub_ring``,
* 07:45:12 ``town:blocked:equipment-slot-flipflop:body``.

Source: each stop's incident capture ``town-arrival/`` (the visit's arrival checkpoint and
journal), copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1c-220-flipflops-1122/ with the life's equipment-visit.jsonl
and loadout-report.jsonl.  Each fixture keeps the arrival policy and sidecars
(support.town_arrival_fixture's format) and only the journal rows its test reads, in order
(``rows.json``: their row numbers in the visit's journal).

    python tests/extract_n1c_220_flipflops_1122_fixtures.py
    (PYTHONPATH: src, tests and the root)
"""
import tests  # noqa: F401 -- isolate runtime files before policy imports

import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.town_arrival_checkpoint import JOURNAL_FILE
from support.town_arrival_fixture import extract

CAPTURES = Path("C:/hengband-backups/pdca/captures/n1c-220-flipflops-1122")
TARGET = Path(__file__).with_name("fixtures") / "n1c-220-flipflops-1122"
CASES = {
    # The Home page of row 131 and the boards around the *Identify* of the 革グローブ.
    "feet": ("20261122-065342-town-blocked-equipment-slot-flipflop-feet", (131, 134, 135)),
    # The visit up to the take-off its target leaves out (row 29 took the 浮遊の指輪 off).
    "sub_ring": ("20261122-072321-town-blocked-equipment-slot-flipflop-sub_ring",
                 tuple(range(30))),
    # The visit's start, then Quest 25's reward and the two *Identify*s (rows 62-65), before
    # the transaction's first move (row 69).
    "body": ("20261122-074512-town-blocked-equipment-slot-flipflop-body",
             (0, 1, 62, 63, 64, 65)),
}


def main() -> None:
    for name, (capture, rows) in CASES.items():
        visit = CAPTURES / capture / "town-arrival"
        target = TARGET / name
        journal = gzip.decompress((visit / JOURNAL_FILE).read_bytes()).splitlines(True)
        with TemporaryDirectory() as raw:
            # extract() keeps a journal prefix: hand it the chosen rows as the journal.
            staged = Path(raw) / "town-arrival"
            staged.mkdir()
            for entry in visit.iterdir():
                if entry.name == JOURNAL_FILE:
                    continue
                if entry.is_dir():
                    (staged / entry.name).mkdir()
                    for inner in entry.iterdir():
                        (staged / entry.name / inner.name).write_bytes(inner.read_bytes())
                else:
                    (staged / entry.name).write_bytes(entry.read_bytes())
            (staged / JOURNAL_FILE).write_bytes(
                gzip.compress(b"".join(journal[row] for row in rows)))
            extract(staged, target, len(rows))
        (target / "rows.json").write_text(json.dumps(list(rows)), encoding="utf-8")
        print(target, sum(path.stat().st_size for path in target.iterdir()))


if __name__ == "__main__":
    main()
