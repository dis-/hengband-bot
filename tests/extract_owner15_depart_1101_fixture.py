"""Freeze n1-c life-092's confirmed loadout at the 13:54 stop (#47, owner15-survival-1101).

Source (read-only, copied from the viewing server by the fix-depart2-1101
diagnosis): C:/hengband-backups/pdca/captures/fix-depart2-1101/n1-c/life-092/
confirmed-loadout.json (the process's jsonlog/confirmed-loadout.json, written
13:54, the item ids of the worn loadout and the optimizer input key it was
confirmed under).  The committed test reads the frozen copy alone.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.extract_dungeon_1031_fixture import sha


SOURCE = Path("C:/hengband-backups/pdca/captures/fix-depart2-1101/n1-c/life-092/confirmed-loadout.json")
OUTPUT = Path(__file__).with_name("fixtures") / "owner15-confirmed-loadout-1101.json"


def main():
    record = json.loads(SOURCE.read_text(encoding="utf-8"))
    frozen = dict(source=SOURCE.name, sha256=sha(SOURCE), record=record)
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(frozen, stream, ensure_ascii=False, indent=1)
        stream.write("\n")
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
