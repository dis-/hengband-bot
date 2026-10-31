"""Freeze the 2026-10-31 21:58 n1-c life-072 oil waste (full lantern refills).

Source: C:/hengband-backups/pdca/captures/n1c-oil-waste-1031/life-072, the
viewing zombie Magic-Eater's state.jsonl and jsonlog/bot-decisions.jsonl.
The worn light is the unidentified 真鍮のランタン {並, Q34} (later {高級品,
Q34}), so its fuel is hidden.

Frozen boards (state.jsonl rows, 0-based):
  910  turn 85412  Yeek cave 1F just after descending (decision 836,
       fundraise:refill-light '\\Fa')
  911  turn 85416  the game's reply: 「ランプに油を注いだ。」「ランプの油は一杯だ。」
       (decision 837 poured again; 838-840 too, all five flasks)
  915  turn 85438  the fifth 「一杯だ」 reply (decision 841, oil 0)
  1152 turn 96693  next town visit, five flasks bought again (decision 1069,
       refill-light '\\Fa')
  1153 turn 96698  the game's reply: 「ランプの油は一杯だ。」 again
and the recorded decision rows' key facts.

Only this extraction tool reads the capture; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

LIFE = Path("C:/hengband-backups/pdca/captures/n1c-oil-waste-1031/life-072")
STATE = LIFE / "state.jsonl"
DECISIONS = LIFE / "jsonlog" / "bot-decisions.jsonl"
OUTPUT = Path(__file__).with_name("fixtures") / "oil-full-lamp-20261031.json.gz"
BOARDS = {910: 85412, 911: 85416, 915: 85438, 1152: 96693, 1153: 96698}
SEQUENCES = (836, 837, 838, 839, 840, 841, 1069, 1070)


def _rows(path: Path):
    with path.open(encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            yield index, line


def main():
    boards = {}
    for index, line in _rows(STATE):
        if index in BOARDS:
            board = json.loads(line)
            assert board["turn"] == BOARDS[index], (index, board["turn"])
            boards[str(board["turn"])] = board
    decisions = {}
    for _index, line in _rows(DECISIONS):
        if '"decision_sequence"' not in line[:200]:
            continue
        row = json.loads(line)
        if row["decision_sequence"] in SEQUENCES and row["turn"] >= 85412:
            decisions[str(row["decision_sequence"])] = {
                key: row[key] for key in
                ("decision_sequence", "turn", "reason", "key", "messages", "fundraising")}
    assert sorted(map(int, decisions)) == list(SEQUENCES), sorted(decisions)
    case = dict(
        source="n1c-oil-waste-1031/life-072 (n1-c zombie Magic-Eater)",
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (STATE, DECISIONS)},
        boards=boards,
        decisions=decisions,
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
