"""Freeze the boards of the self-knowledge quaff test (self-knowledge-quaff-1113).

Source: the viewing server's ~/hengbot-soak/n1-c/life-205/state.jsonl (Magic-Eater,
Lv38), copied read-only line by line (``sed -n "1271p;3538p"``) into a scratch file:

  dungeon  line index 1270, turn 2239207: Angband 62F (quest 46), no visible
           monster, not blind or confused; slot g 自己分析の薬 (75/58, aware), picked
           up at turn 2238669 (「ザック中: 自己分析の薬(h)。」).  The recorded bot
           answered ``7`` explore (jsonlog/bot-decisions.jsonl).
  town     line index 3537, turn 2250815: the Outpost after the Recall, no visible
           monster; the potion in slot i.  The recorded bot answered ``3``
           shop:approach.

The life carried the potion on 2048 such boards (index 1178 to 3537) and never drank
it: consumable_policy.USE_UNSUPPORTED kept the 「拾って使う」 row out of the stat-gain
quaff.  The fixture is a JSON-lines gzip, one {"id", "line"} record per board.

    python tests/extract_n1c_205_self_knowledge_1113_fixture.py <two-line scratch file>
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "n1c-205-self-knowledge-1113.jsonl.gz"
IDS = ("dungeon/1270", "town/3537")


def main(source: Path) -> None:
    lines = source.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(IDS), len(lines)
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        for record_id, line in zip(IDS, lines):
            stream.write(json.dumps({"id": record_id, "line": line}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
