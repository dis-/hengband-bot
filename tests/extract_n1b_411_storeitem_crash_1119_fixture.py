"""Extract tests/fixtures/n1b-411-storeitem-crash-1119/.

Source: n1-b life-411 (Magic-Eater Lv50) crashed 2026-11-19 22:14:22 with ``AttributeError:
'StoreItem' object has no attribute 'is_wand_staff'``.  Incident capture
20261119-221422-crash-attributeerror-storeitem-object-has-no-attribute-is-wa and its town-arrival
checkpoint 20261119-221408.228059368-turn9340079 (turn 9,340,079), copied to the implementer's
``.scratch/capture/`` and ``.scratch/town-arrival/``.

* the checkpoint with all 37 journal rows (decisions 7983-8019, the last ``shop:approach`` to
  the Magic shop);
* ``crash-board.json.xz``: the capture's last board (state.jsonl, the Magic shop's screen), on
  which the next decision crashed.  The crash left it out of the journal.

    python tests/extract_n1b_411_storeitem_crash_1119_fixture.py
"""
import gzip
import lzma
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

SCRATCH = Path(__file__).resolve().parents[1] / ".scratch"
VISIT = SCRATCH / "town-arrival" / "20261119-221408.228059368-turn9340079"
CAPTURE = (SCRATCH / "capture"
           / "20261119-221422-crash-attributeerror-storeitem-object-has-no-attribute-is-wa")
TARGET = Path(__file__).with_name("fixtures") / "n1b-411-storeitem-crash-1119"


def main() -> None:
    extract(VISIT, TARGET, 37)
    last = gzip.decompress((CAPTURE / "state.jsonl.gz").read_bytes()).splitlines()[-1]
    (TARGET / "crash-board.json.xz").write_bytes(lzma.compress(last, preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
