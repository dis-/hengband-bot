"""Freeze the boards of the *Remove Curse* reserve test (star-remove-curse-reserve-1102).

Sources (copied read-only from the viewing bots, C:/hengband-backups/pdca/captures):

  warrior  n1-a life-440 (class 0, gold 15688), state lines of
           recall-yeek-1030/n1-a/life-440/captures/20261030-205859-stuck-
           prompt-town-recall-to-yeek-cave:
             74 (turn 401437) outside, on the Temple entrance (31, 77);
             75 the Temple page, ware o *解呪*の巻物 (70/15, 6072 gold);
             80 (turn 401891) the Home page, 11 rows and no *Remove Curse*.
           The recorded bot (before the 2026-11-02 table) bought o there
           (``po\\r`` shop:in-store-buy, gold 15688 -> 9616) and deposited
           it at Home (``dg\\x1b`` home:atomic-deposit, line 81).
  me       n1-c life-092 (class 16, the Magic-Eater), state lines of
           fix-depart2-1101/n1-c/life-092/captures/20261101-131854-stuck-
           prompt-quest-strategy-ranged-fire-magic-eater: the outside board
           on the Temple entrance before line 75 and the Temple page 75,
           ware p *解呪*の巻物.

The fixture is a JSON gzip: {"warrior": {...}, "me": {...}} with the named
boards and the store entrances of the board.  Only this tool reads the
captures.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

CAPTURES = Path("C:/hengband-backups/pdca/captures")
SOURCES = {
    "warrior": ("recall-yeek-1030/n1-a/life-440/captures/20261030-205859-stuck-"
                "prompt-town-recall-to-yeek-cave/state.jsonl.gz",
                {"outside": 74, "temple": 75, "home": 80}),
    "me": ("fix-depart2-1101/n1-c/life-092/captures/20261101-131854-stuck-"
           "prompt-quest-strategy-ranged-fire-magic-eater/state.jsonl.gz",
           {"outside": 74, "temple": 75}),
}
OUTPUT = Path(__file__).with_name("fixtures") / "star-remove-curse-reserve-20261102.json.gz"


def main() -> None:
    cases = {}
    for name, (path, boards) in SOURCES.items():
        with gzip.open(CAPTURES / path, "rt", encoding="utf-8") as stream:
            lines = stream.read().split("\n")
        named = {board: json.loads(lines[index]) for board, index in boards.items()}
        cells = named["outside"]["grid_map"]["cells"]
        cases[name] = dict(source=path, lines=boards, boards=named,
                           store_cells=[[c["y"], c["x"], c["s"]] for c in cells if "s" in c])
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(cases, stream, ensure_ascii=False)


if __name__ == "__main__":
    main()
