"""Freeze the n1-b life-370 loot / choke / Anaguma loop of 2026-11-11 (tests/test_n1b_370_loot_choke_1111_recorded.py).

Source: the viewing Magic-Eater n1-b life-370 (Lv 42), オークの洞窟23階 (floor (3, 23, 0)),
stopped with ``loop-detected`` at 15:32:10 (build bot-ba6ab7e55).  Copied read-only from the
viewing server to C:/hengband-backups/pdca/captures/n1b-370-loot-choke-1111:

  state.jsonl.gz                  the 69 player-turn boards before the stop
  bot-decisions.jsonl.gz          their decision rows
  incident/policy-state.json      the stop's policy summary (the absorption record, the floor's uses)

Only this extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
import lzma
from pathlib import Path


ROOT = Path("C:/hengband-backups/pdca/captures/n1b-370-loot-choke-1111")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-370-loot-choke-1111.json.xz"


def main():
    with gzip.open(ROOT / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [row for row in map(json.loads, stream) if row.get("type") == "player_turn"]
    decisions = []
    with gzip.open(ROOT / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("turn", 0) >= boards[0]["turn"]:
                decisions.append({"turn": row["turn"], "reason": row["reason"], "key": row["key"],
                                  "position": row.get("position")})
    state = json.loads((ROOT / "incident" / "policy-state.json").read_text(encoding="utf-8"))["state"]
    fixture = {
        "source": "20261111-153213-loop-detected (copied from the viewing server)",
        "boards": boards,
        "decisions": decisions,
        "absorbed": state["_me_staff_sequence"]["absorbed"],
        "floor_uses": state["_me_power_floor"]["uses"],
    }
    payload = json.dumps(fixture, ensure_ascii=False, sort_keys=True).encode("utf-8")
    OUTPUT.write_bytes(lzma.compress(payload, preset=9))
    print(OUTPUT.name, len(boards), len(decisions), OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
