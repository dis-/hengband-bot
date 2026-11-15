"""Extract tests/fixtures/n1b-405-disintegrate-1116.json.xz.

Source: the viewing Magic-Eater n1-b life-405 (Lv44, Castle 62F-64F, 2026-11-16 01:58-02:01),
copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-405-disintegrate-1116/:

- boards.jsonl: the boards of the named turns, taken from
  life-405/jsonlog/snapshots/snapshots-20261116-015517-8d95c7.jsonl.gz and
  snapshots-20261116-020757-b8d55c.jsonl.gz;
- mbz-decisions.jsonl: every row of life-405/jsonlog/bot-decisions.jsonl whose key fired the
  absorbed 分解 (``mBz``);
- first-frame.jsonl: the first row of spectate-frames.jsonl (decision 29803, turns
  3484926-3485739), the earliest absorbed device lists still kept (``magic_eater_powers``):
  the frames of the decisions themselves had already rolled away.

The fixture keeps the boards of the named decisions, their recorded rows and those lists.

    python tests/extract_n1b_405_disintegrate_1116_fixture.py <copy-dir>
"""
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "n1b-405-disintegrate-1116.json.xz"
SEQUENCES = (25576, 25766, 26312, 26956)


def main() -> None:
    root = Path(sys.argv[1])
    rows = {}
    for line in (root / "mbz-decisions.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["decision_sequence"] in SEQUENCES:
                rows[row["decision_sequence"]] = row
    boards = {}
    for line in (root / "boards.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            board = json.loads(line)
            boards[board["turn"]] = board
    frame = json.loads((root / "first-frame.jsonl").read_text(encoding="utf-8"))
    cases = {}
    for sequence in SEQUENCES:
        row = rows[sequence]
        cases[str(sequence)] = {"board": boards[row["turn"]],
                                "decision": {"turn": row["turn"], "reason": row["reason"],
                                             "key": row["key"]}}
    payload = {"cases": cases, "lists": frame["magic_eater_powers"],
               "lists_decision": frame["decision_sequence"]}
    OUTPUT.write_bytes(lzma.compress(json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        preset=9 | lzma.PRESET_EXTREME))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
