"""Freeze the disenchant-1105 boards (tests/fixtures/disenchant-1105.json.gz).

Source (read-only, on the viewing server, 2026-11-05): state.jsonl and
jsonlog/bot-decisions.jsonl of
 * mobile: n1-b life-306 (warrior Lv26, 鉄獄19階), an awake チョウチョアルコウのアンデッド
   (race 913, BR_DISE), turns 4859632..4859664: recorded ``hunt`` then ``melee``.
 * mold: n1-c life-140 (Magic-Eater Lv42, オークの洞窟23階), a 劣化モルド (race 192,
   NEVER_MOVE, UN_BONUS), asleep at 3246104 and awake at 3246111: recorded
   ``ranged:fire-offset``, which woke it.

Usage: extract_disenchant_fixture.py <boards.json.gz> <out.json.gz>; the input maps
"<instance>/<life>/<race>" to the raw state lines holding that race in view.  Only this
tool reads the logs; the committed test reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import json
import sys

MOBILE_ROWS = [(3238, 4859632, "hunt", "4"), (3239, 4859643, "melee", "1"),
               (3240, 4859654, "melee", "1"), (3241, 4859664, "melee", "1")]
MOLD_ROWS = [(9594, 3246104, "ranged:fire-offset", "fr*p744444t5\x1b")]
CASES = {"mobile": ("n1-b/life-306/913", 4, MOBILE_ROWS),
         "mold": ("n1-c/life-140/192", 2, MOLD_ROWS)}


def main(source: str, target: str) -> None:
    with gzip.open(source, "rt", encoding="utf-8") as stream:
        lines = json.load(stream)
    frozen = {}
    for name, (where, count, rows) in CASES.items():
        frozen[name] = {
            "boards": [json.loads(line) for line in lines[where][:count]],
            "decisions": [dict(zip(("decision_sequence", "turn", "reason", "key"), row))
                          for row in rows],
        }
    with gzip.open(target, "wt", encoding="utf-8") as stream:
        json.dump(frozen, stream, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
