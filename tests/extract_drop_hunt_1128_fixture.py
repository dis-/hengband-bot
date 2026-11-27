"""Extract tests/fixtures/drop-hunt-1128/ (tests/test_drop_hunt_1128_recorded.py).

Source: n1-b life-419 (Magic-Eater CL50, Angband 80F, permanent speed +17 under the unmet +25
row), read-only copies of the viewing server's snapshot logs in
C:/hengband-backups/pdca/captures/drop-hunt-1128/ (copied 2026-11-28 from
~/hengbot-soak/n1-b/life-419/jsonlog/snapshots/):

  snapshots-20261128-060152-4173b6.jsonl.gz   05:52: ソーラー (race 943, L64, DROP_GOOD) almost
                                              dead 2 off; the recorded decision 14477853 cast
                                              the absorbed *Destruction* before a Teleport Away
  snapshots-20261128-043135-7e8a1b.jsonl.gz   04:22: ナイトウォーカー (race 768, L59, DROP_GOOD)
                                              wounded 2 off; the recorded decision 14221566 cast
                                              *Destruction*
  snapshots-20261128-041517-69ccdc.jsonl.gz   03:57: 『アトラク・ナクア』 (race 809, L75) 4 off after
                                              a loss of 422 (HP 706/1128); the recorded decision
                                              14151005 was the emergency ladder's *Destruction*

and the live decision log rows of those floors (n1b-419-decisions-drop-hunt.jsonl, from
bot-decisions.jsonl*).  Kept: the player-turn boards of each replay window, xz-compressed.
The absorbed-power lists are tests/fixtures/loot-before-destruction-1128/me-device-lists.json.xz
(the same life's checkpoint 20261128-050851).

    python tests/extract_drop_hunt_1128_fixture.py
"""
import gzip
import json
import lzma
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/drop-hunt-1128")
FIXTURE = Path(__file__).with_name("fixtures") / "drop-hunt-1128"
WINDOWS = (
    ("snapshots-20261128-060152-4173b6.jsonl.gz", 14477600, 14477853, "boards-solar.jsonl.xz"),
    ("snapshots-20261128-043135-7e8a1b.jsonl.gz", 14221300, 14221566, "boards-nightwalker.jsonl.xz"),
    ("snapshots-20261128-041517-69ccdc.jsonl.gz", 14150800, 14151005, "boards-atlach.jsonl.xz"),
)


def main():
    FIXTURE.mkdir(exist_ok=True)
    for source, first, last, target in WINDOWS:
        boards = []
        with gzip.open(ROOT / source, "rt", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue  # the log's last line may be cut
                if row.get("type") == "player_turn" and first <= row["turn"] <= last:
                    boards.append(json.dumps(row, ensure_ascii=False))
        (FIXTURE / target).write_bytes(
            lzma.compress(("\n".join(boards) + "\n").encode("utf-8"), preset=9))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
