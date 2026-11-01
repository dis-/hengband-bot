"""Freeze the boards of the unwanted-kinds test (cheap-books-1102).

Sources (copied read-only from the viewing bots):

  arrival  n1-c life-072 (Magic-Eater, class 16), state line 78 (turn
           1657801): the first town board (the Outpost, store closed) after
           the Recall it read on Yeek Cave 13F (decision ``rj``
           ``return:recall``, turn 1657558), its pack of 22 stacks holding
           three first books, slot a
           Lv1 ヘックスの魔法書 x2 (tval 107 sval 0), b 武芸の書 (106/0) and
           c 暗黒の魔法書 (94/0).  C:/hengband-backups/pdca/captures/
           fix-me-powerful-stuck-1101/life-072/captures/
           20261031-235613-stuck-prompt-me-powerful-uncurse/state.jsonl.gz
  character  n1-c life-056: the periodic character response (turn 222141)
           whose sheet lists the Magic-Eater's realms: none (``[]``).
           C:/hengband-backups/pdca/captures/latest-12h-1031/n1-c/life-056/
           captures/20261031-082432-exit-no-marker/state.jsonl.gz

The fixture is a JSON-lines gzip: line 0 the arrival board, line 1 the
character response.  Only this extraction tool reads the captures.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

CAPTURES = Path("C:/hengband-backups/pdca/captures")
ARRIVAL = (CAPTURES / "fix-me-powerful-stuck-1101/life-072/captures"
          / "20261031-235613-stuck-prompt-me-powerful-uncurse/state.jsonl.gz", 78)
CHARACTER = CAPTURES / ("latest-12h-1031/n1-c/life-056/captures/"
                        "20261031-082432-exit-no-marker/state.jsonl.gz")
OUTPUT = Path(__file__).with_name("fixtures") / "cheap-books-20261102.jsonl.gz"


def main() -> None:
    path, index = ARRIVAL
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        board = stream.read().split("\n")[index]
    assert json.loads(board)["turn"] == 1657801
    with gzip.open(CHARACTER, "rt", encoding="utf-8") as stream:
        character = next(line for line in stream
                         if json.loads(line).get("type") == "character")
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        stream.write(board + "\n" + character + "\n")


if __name__ == "__main__":
    main()
