"""Extract tests/fixtures/n1c-215-sensed-paralyzer-1116.json.xz.

Source: the viewing Magic-Eater n1-c life-215 (Lv25, 迷宮 (dungeon 4) 17F), its death of
2026-11-16 11:24:26 (stop ``exit-no-marker``), copied read-only from the viewing server
(life-215/captures/20261116-112424-exit-no-marker/) to
C:/hengband-backups/pdca/captures/n1c-deaths-1116/life-215/20261116-112424-exit-no-marker/:

- state.jsonl.gz: the boards up to the death;
- bot-decisions.jsonl.gz: the decisions up to the death.

The fixture keeps the board of decision 35288 (turn 1224013), the first after the arrival's
邪悪感知 (decision 35287), with the sleeping ゲイザー sensed at [14,22], and the decision posted
on it.

    python tests/extract_n1c_215_sensed_paralyzer_1116_fixture.py <capture-dir>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "n1c-215-sensed-paralyzer-1116.json.xz"
TURN = 1224013


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    root = Path(sys.argv[1])
    board = next(row for row in _rows(root / "state.jsonl.gz") if row["turn"] == TURN)
    decision = next(row for row in _rows(root / "bot-decisions.jsonl.gz") if row["turn"] == TURN)
    payload = {"board": board,
               "decision": {key: decision[key]
                            for key in ("decision_sequence", "turn", "reason", "key")}}
    OUTPUT.write_bytes(lzma.compress(json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        preset=9 | lzma.PRESET_EXTREME))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
