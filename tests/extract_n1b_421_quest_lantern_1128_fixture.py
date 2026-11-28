"""Extract tests/fixtures/n1b-421-quest-lantern-1128.jsonl.xz (tests/test_n1b_421_quest_lantern_1128_recorded.py).

Source: n1-b life-421 (Klackon Magic-Eater; build bot-b81760a38) on hengband.net, read-only:
``~/hengbot-soak/n1-b/life-421/state.jsonl`` (its last 250 rows) and the first 149 rows of
``jsonlog/snapshots/snapshots-20261128-100000-072576.jsonl.gz`` (the birth of the 09:34 restart),
copied to C:/hengband-backups/pdca/captures/n1b-421-quest-lantern-1128/.

Kept: the player-turn boards of the birth (turn 1, CL1 in the Outpost) and the boards from the
Outpost board before the Q34 request (4961288) to the first board on the emptied lantern cell
(4961463), xz-compressed.

    python tests/extract_n1b_421_quest_lantern_1128_fixture.py
"""
import json
import lzma
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/captures/n1b-421-quest-lantern-1128")
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-421-quest-lantern-1128.jsonl.xz"
FIRST, LAST = 4961288, 4961463


def main():
    rows = []
    birth = [json.loads(line) for line in (SOURCE / "n1b-421-birth-149.jsonl").read_text(
        encoding="utf-8").splitlines() if line.strip()]
    rows += [row for row in birth if row.get("type") == "player_turn" and row["turn"] == 1][:1]
    for line in (SOURCE / "n1b-421-state-tail-250.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("type") == "player_turn" and FIRST <= row["turn"] <= LAST:
            rows.append(row)
    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
    FIXTURE.write_bytes(lzma.compress(text.encode("utf-8"), preset=9))
    print(FIXTURE.name, len(rows), FIXTURE.stat().st_size)


if __name__ == "__main__":
    main()
