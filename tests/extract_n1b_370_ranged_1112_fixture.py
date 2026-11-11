"""Extract tests/fixtures/n1b-370-ranged-1112.json.xz.

Source: the viewing Magic-Eater n1-b life-370 (Lv45, Castle 64F, 2026-11-12 02:06),
copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-370-ranged-1112/:

- n1b370-snap-current.jsonl.gz: life-370/jsonlog/snapshots/snapshots-current.jsonl.gz
  (the boards of turns 8940870-8962157);
- n1b370-frames.jsonl: spectate-frames.jsonl (decisions 34173-34382, each with the
  absorbed device lists the live policy last saw, ``magic_eater_powers``);
- n1b370-dec.jsonl: the tail of life-370/jsonlog/bot-decisions.jsonl (sequence -> turn).

The fixture keeps the boards of the named decisions, their recorded rows, the device
lists of each and the monster knowledge (lib/edit/MonraceDefinitions.jsonc) of every
race on them.

    python tests/extract_n1b_370_ranged_1112_fixture.py <copy-dir>
"""
import gzip
import json
import lzma
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import load_monrace_knowledge

OUTPUT = Path(__file__).with_name("fixtures") / "n1b-370-ranged-1112.json.xz"
GAME = Path("C:/hengband/lib/edit")
SEQUENCES = (34173, 34326)


def main() -> None:
    root = Path(sys.argv[1])
    frames = {}
    for line in (root / "n1b370-frames.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            frames[row["decision_sequence"]] = row
    rows = {}
    with open(root / "n1b370-dec.jsonl", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                continue  # the copy starts mid-line
            if row.get("decision_sequence") in SEQUENCES:
                rows[row["decision_sequence"]] = row
    turns = {rows[sequence]["turn"]: sequence for sequence in SEQUENCES}
    boards = {}
    with gzip.open(root / "n1b370-snap-current.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                board = json.loads(line)
            except ValueError:
                continue  # the copy was taken while the file grew
            if board.get("turn") in turns and board["turn"] not in boards:
                boards[board["turn"]] = board
    races = load_monrace_knowledge(GAME / "MonraceDefinitions.jsonc")
    ids = {monster["race_id"] for board in boards.values()
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    cases = {}
    for turn, sequence in turns.items():
        row, frame = rows[sequence], frames[sequence]
        assert (row["reason"], row["key"]) == (frame["reason"], frame["key"].replace("\\e", "\x1b"))
        cases[str(sequence)] = {"board": boards[turn],
                                "decision": {"turn": turn, "reason": row["reason"], "key": row["key"]},
                                "lists": frame["magic_eater_powers"]}
    payload = {"cases": cases, "monraces": {key: asdict(races[key]) for key in sorted(ids)}}
    OUTPUT.write_bytes(lzma.compress(json.dumps(
        payload, ensure_ascii=False, default=sorted, separators=(",", ":")).encode("utf-8"),
        preset=9 | lzma.PRESET_EXTREME))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
