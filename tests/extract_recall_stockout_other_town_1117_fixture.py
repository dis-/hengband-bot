"""Extract tests/fixtures/recall-stockout-other-town-1117/.

Source (copied read-only from the viewing server to
C:/hengband-backups/pdca/recall-stockout-other-town-1117/):

* ``n1c-216-0846/``: n1-c life-216's town-arrival checkpoint of 2026-11-17 08:46:19
  (Magic-Eater, turn 4,544,996, 1,277,741 gold, returned by Word of Recall from Angband
  77F), the ``town-arrival/`` of incident capture 20261117-084726-loop-detected.  Journal
  rows 0-165 are kept: row 165 is the visit's Word of Recall read
  (``town:recall-to-angband``) after its Black Market purchases (rows 145-159).
* ``pages-1504.jsonl.xz``: three boards of the same life's town visit of 2026-11-17
  15:04 from the server's snapshot log (snapshots-20261117-150555-760742.jsonl.gz): the
  Alchemist page after its purchase (turn 5,565,877, no Word of Recall), the Temple page
  after the purchase of its last two Word of Recall (turn 5,565,931, the page live
  answered ``town:recall-stockout-mining``) and the first board outside (turn
  5,565,936).

DECLARED LOSS: the 15:04 visit's own town-arrival checkpoint had rotated away on the
server; the pages are decided on the 08:46 arrival's policy (the same character).

    python tests/extract_recall_stockout_other_town_1117_fixture.py
"""
import json
import lzma
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

SOURCE = Path("C:/hengband-backups/pdca/recall-stockout-other-town-1117")
VISIT = SOURCE / "incident" / "20261117-084726-loop-detected" / "town-arrival"
TARGET = Path(__file__).with_name("fixtures") / "recall-stockout-other-town-1117"
ROWS = 166
ALCHEMIST = (5565877, 2567168)  # (turn, gold) after the purchase
TEMPLE_TURN = 5565931


def pages() -> bytes:
    store_pages = [json.loads(line) for line in
                   (SOURCE / "visit-store-pages-1504.jsonl").read_text(encoding="utf-8").splitlines()]
    alchemist = next(board for board in store_pages
                     if (board["turn"], board["player"]["gold"]) == ALCHEMIST)
    temple = [board for board in store_pages if board["turn"] == TEMPLE_TURN][-1]
    outside = json.loads((SOURCE / "outside-after-1504.jsonl").read_text(
        encoding="utf-8").splitlines()[0])
    return "".join(json.dumps(board, ensure_ascii=False) + "\n"
                   for board in (alchemist, temple, outside)).encode("utf-8")


def main() -> None:
    extract(VISIT, TARGET / "n1c-216-0846", ROWS)
    (TARGET / "pages-1504.jsonl.xz").write_bytes(lzma.compress(pages(), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.rglob("*") if path.is_file()))


if __name__ == "__main__":
    main()
