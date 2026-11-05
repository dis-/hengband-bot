"""Freeze the n1-b life-321 light-radius-0 stops (2026-11-06 02:01 and 02:06).

Source: C:/hengband-backups/pdca/captures/n1b-321-light-1106/ (copied from the viewing
bot; Magic-Eater Lv34, resumed from life-319/317).  At 23:18 on 11-05 the equipment
optimizer put on the just identified ★火消しライター (TR_LITE_M1, TR_DARK_SOURCE,
+3 stealth) and put the ★ガラドリエルの玻璃瓶 in Home: light radius 0 from then on.

* town: the 02:01:08 arrival checkpoint (incident 20261106-020156-loop-detected) and its
  journal up to the third refused Recall read (row 193).
* dig: the 02:05:41 arrival checkpoint (incident 20261106-020626-loop-detected), its
  journal (to the descent), the dungeon boards of Yeek cave 1F from the floor arrival
  to the first board after the granite tunnel finished (turn 2596574), the recorded
  decision rows of those boards, and the capture's Magic-Eater power uses on the floor.
Only this tool reads the capture.

    python tests/extract_n1b_321_zero_light_1106_fixtures.py
"""

from __future__ import annotations

from collections import defaultdict
import gzip
import io
import json
from pathlib import Path
import tarfile

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/n1b-321-light-1106")
FIXTURES = Path(__file__).with_name("fixtures") / "n1b-321-zero-light-1106"
TOWN = ROOT / "incident-captures" / "20261106-020156-loop-detected"
DIG = ROOT / "incident-captures" / "20261106-020626-loop-detected"
TOWN_ROWS = 194
FLOOR_TURN = 2595869  # the descent's landing on Yeek cave 1F
DUG_TURN = 2596574    # 「穴を掘り終えた。」, then 「そこは掘れない。」 x12
DECISION_FACTS = ("decision_sequence", "turn", "reason", "key")


def _add(tar, name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def _checkpoint(tar, capture: Path, rows: int | None) -> None:
    visit = capture / "town-arrival"
    _add(tar, "policy.pkl", (visit / "policy.pkl").read_bytes())
    _add(tar, "sidecars.json", (visit / "sidecars.json").read_bytes())
    for path in sorted((visit / "sidecars").iterdir()):
        _add(tar, f"sidecars/{path.name}", path.read_bytes())
    with gzip.open(visit / "journal.jsonl.gz", "rt", encoding="utf-8") as stream:
        kept = [line for index, line in enumerate(stream) if rows is None or index < rows]
    _add(tar, "journal.jsonl.gz", gzip.compress("".join(kept).encode("utf-8"), mtime=0))


def _dungeon_case() -> dict:
    """The floor's boards, each paired with the decision row recorded on it."""
    decisions = []
    with open(ROOT / "jsonlog" / "bot-decisions.jsonl", encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("key") and FLOOR_TURN <= row.get("turn", 0) <= DUG_TURN:
                decisions.append({key: row.get(key) for key in DECISION_FACTS})
    decisions = decisions[: next(index for index, row in enumerate(decisions)
                                 if row["turn"] == DUG_TURN) + 1]
    boards = defaultdict(list)
    for row in ring_rows((DIG / "snapshots" / "snapshots-current.jsonl.gz").read_bytes()):
        if row.get("type") == "player_turn" and row["turn"] >= FLOOR_TURN:
            boards[row["turn"]].append(row)
    per_turn = defaultdict(int)
    for row in decisions:
        per_turn[row["turn"]] += 1
    taken = defaultdict(int)
    paired = []
    for row in decisions:
        # A board re-emitted on the same turn (a message-only update) precedes the
        # one the decision was made on: take the last boards of each turn.
        turn = row["turn"]
        offset = len(boards[turn]) - (per_turn[turn] if turn != DUG_TURN else len(boards[turn]))
        paired.append({"decision": row, "board": boards[turn][offset + taken[turn]]})
        taken[turn] += 1
    state = json.loads((DIG / "policy-state.json").read_text(encoding="utf-8"))
    return {"boards": paired, "me_power_uses": state["state"]["_me_power_floor"]["uses"]}


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    with tarfile.open(FIXTURES / "town.tar.xz", "w:xz", preset=9) as tar:
        _checkpoint(tar, TOWN, TOWN_ROWS)
    with tarfile.open(FIXTURES / "dig.tar.xz", "w:xz", preset=9) as tar:
        _checkpoint(tar, DIG, None)
        case = json.dumps(_dungeon_case(), ensure_ascii=False, separators=(",", ":"))
        _add(tar, "dungeon.json.gz", gzip.compress(case.encode("utf-8"), mtime=0))
    for path in sorted(FIXTURES.iterdir()):
        print(path, path.stat().st_size)


if __name__ == "__main__":
    main()
