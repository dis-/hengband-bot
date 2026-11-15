"""Extract tests/fixtures/n1b-401-loop-1115.jsonl.gz.

Source: n1-b life-401 (Lv37 Magic-Eater), Angband 49F, 2026-11-15 17:17:17-17:17:42, the
automatic incident capture of its first loop stop (incident-captures/20261115-171742-loop-detected),
copied read-only from the viewing server to C:/hengband-backups/pdca/n1b-401-loop-1115/inc-171742.
Kept: the latest ~f skill list the process read before the visit, the 49F boards from the arrival
by Recall (turn 1981261) to the stop (turn 1981656), and the recorded (turn, decision, reason, key)
of the same window.

The capture's live generation is a copied tail: it starts inside a gzip member, so the members are
decoded from the first whole one on.

    python tests/extract_n1b_401_loop_1115_fixture.py
"""
import gzip
import json
import zlib
from pathlib import Path

CAPTURE = Path("C:/hengband-backups/pdca/n1b-401-loop-1115/inc-171742")
GENERATION = CAPTURE / "snapshots" / "snapshots-current.jsonl.gz"
TARGET = Path(__file__).with_name("fixtures") / "n1b-401-loop-1115.jsonl.gz"
ARRIVAL, LAST = 1981261, 1981656


def _lines(path):
    data = path.read_bytes()
    position, chunks = data.find(b"\x1f\x8b\x08"), []
    while 0 <= position < len(data):
        stream = zlib.decompressobj(31)
        try:
            chunks.append(stream.decompress(data[position:]))
        except zlib.error:
            position = data.find(b"\x1f\x8b\x08", position + 1)
            continue
        if not stream.unused_data:
            break
        position = len(data) - len(stream.unused_data)
    return b"".join(chunks).split(b"\n")


def main() -> None:
    skill, boards = None, []
    for line in _lines(GENERATION):
        try:
            board = json.loads(line)
        except ValueError:
            continue  # the tail's cut line
        if (board.get("knowledge") or {}).get("category") == "skill_exp" and board["turn"] < ARRIVAL:
            skill = board
        elif board.get("type") == "player_turn" and ARRIVAL <= board["turn"] <= LAST:
            boards.append(board)
    assert {board["floor"]["level"] for board in boards} == {49}
    turns = {board["turn"] for board in boards}
    rows = [{"role": "skill-knowledge", "board": skill}]
    rows += [{"role": "board", "board": board} for board in boards]
    with open(CAPTURE / "decision-tail.jsonl", encoding="utf-8") as fh:
        for line in fh:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue  # the tail's first line is cut
            if record.get("turn") in turns:
                rows.append({"role": "decision", "decision": {
                    key: record[key] for key in ("turn", "decision_sequence", "reason", "key")}})
    with gzip.GzipFile(TARGET, "wb", mtime=0) as out:
        for row in rows:
            out.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(TARGET, TARGET.stat().st_size, len(rows), boards[0]["turn"], boards[-1]["turn"])


if __name__ == "__main__":
    main()
