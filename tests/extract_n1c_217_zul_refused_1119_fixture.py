"""Extract tests/fixtures/n1c-217-zul-refused-1119/.

Source: n1-c life-217's stop of 2026-11-19 01:14:29 (Magic-Eater Lv35, turn 3,166,824,
``quest:blocked:me-staff``), copied read-only from the viewing server to
C:/hengband-backups/pdca/n1c-217-me-staff-1119/: the incident capture's ``town-arrival/``
(the Outpost arrival of 01:13:42, turn 3,147,682, the start town of the Zul walk; journal row
0 is kept) and the last board of the stop capture's ``state.jsonl.gz`` (Zul after the cure,
the refused '<': 「敵がすぐ近くにいるときは広域マップに入れない！」).

The second stop (2026-11-19 01:49:49, build bot-b94db342c, the first fix in): the restart's
town-arrival checkpoint in Zul (01:49:41, turn 3,166,824, ``arrival2/``), all 25 journal rows,
to ``n1c-217-zul-unseen-1119/``: nine refusals at (20,68) with the waits between them, then
the same stop.

    python tests/extract_n1c_217_zul_refused_1119_fixture.py
"""
import gzip
import lzma
from pathlib import Path

from support.town_arrival_fixture import extract

SOURCE = Path("C:/hengband-backups/pdca/n1c-217-me-staff-1119")
VISIT = SOURCE / "incident" / "town-arrival"
TARGET = Path(__file__).with_name("fixtures") / "n1c-217-zul-refused-1119"
ROWS = 1
RESTART = SOURCE / "arrival2"
RESTART_TARGET = Path(__file__).with_name("fixtures") / "n1c-217-zul-unseen-1119"
RESTART_ROWS = 25


def main() -> None:
    extract(VISIT, TARGET, ROWS)
    with gzip.open(SOURCE / "capture" / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        last = stream.read().splitlines()[-1]
    (TARGET / "stop-board.json.xz").write_bytes(lzma.compress(last.encode("utf-8")))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))
    extract(RESTART, RESTART_TARGET, RESTART_ROWS)
    print(sorted((path.name, path.stat().st_size) for path in RESTART_TARGET.iterdir()))


if __name__ == "__main__":
    main()
