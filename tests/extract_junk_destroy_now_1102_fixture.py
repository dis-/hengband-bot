"""Freeze the boards of the junk-destroy-now test (junk-destroy-now-1102).

Sources: the viewing Magic-Eater n1-c life-093 (class 16, no realm) on the
server, ~/hengbot-soak/n1-c/life-093/state.jsonl, copied read-only to
C:/hengband-backups/pdca/captures/junk-destroy-now-1102/n1-c/life-093/:

  book     state line 600 (turn 1561402, Yeek Cave 13F, no visible monster,
           HP 173/248): the board right after it picked up 武芸の書
           (tval 106 sval 0, now slot a); slot b 匠の魔法書 (97/0) was
           already carried.  The bot walked on with both books.
  cursed   state line 2408 (turn 1582337, Angband 13F, no visible monster,
           HP 267/267): the board right after it identified the hard leather
           cap it had just picked up (slot l, tval 32 sval 2) as cursed
           (is_cursed/is_broken), with three first books in slots a-c.
  character  the first character response of the same life (turn 1554736):
           realms ``[]``.
  monster  n1-c life-100 state line 937 (turn 1465849): its one visible
           monster entry (a fleeing cave orc, race 126), copied for the
           DECLARED CONSTRUCTED hostile control.

The fixture is a JSON-lines gzip: book, cursed, character, monster.  Only
this extraction tool reads the captures.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

CAPTURES = Path("C:/hengband-backups/pdca/captures/junk-destroy-now-1102/n1-c")
LIFE_093 = CAPTURES / "life-093"
OUTPUT = Path(__file__).with_name("fixtures") / "junk-destroy-now-20261102.jsonl.gz"


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").rstrip("\n").split("\n")


def main() -> None:
    early = _lines(LIFE_093 / "state-lines-598-602-and-character.jsonl")
    book, character = early[2], early[5]
    cursed = _lines(LIFE_093 / "state-lines-2406-2410.jsonl")[2]
    monster = _lines(CAPTURES / "life-100" / "state-line-937.jsonl")[0]
    assert json.loads(book)["turn"] == 1561402
    assert json.loads(cursed)["turn"] == 1582337
    assert json.loads(character)["type"] == "character"
    assert json.loads(monster)["turn"] == 1465849
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join((book, cursed, character, monster)) + "\n")


if __name__ == "__main__":
    main()
