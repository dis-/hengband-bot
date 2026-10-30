"""Freeze the 2026-10-30 08:28 n1-c life-010 town emergency-recall stop (D22).

Source: the automatic capture incident-captures/20261030-082816-stuck-prompt
of the viewing Magic-Eater n1-c life-010 (Lv8, town, HP 14/129 beside the
town unique 鳩『ポッポ』).  Decision 6186 chose ``emergency:recall`` and
posted ``rc``; the game asked 「どのダンジョンに帰還しますか:」 and the
operation stopped unowned (stuck-prompt x3 -> escalate).

The snapshot ring copy is the 16 MiB tail of a multi-member gzip: it begins
inside a member, so decoding starts at the first member header and keeps
whole members only.  Frozen: the stop board (turn 479582, the ring's last
player_turn row), the last skill-proficiency knowledge row the process
consumed before it (turn 478572), the recorded decision 6186 facts, and the
monster knowledge of the board's monsters.

Only this extraction tool reads the capture; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import zlib
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


CAPTURE = Path(
    "C:/hengband-backups/viewing-captures-1030/n1c-lives-8-13/life-010/"
    "incident-captures/20261030-082816-stuck-prompt")
RING = CAPTURE / "snapshots" / "snapshots-current.jsonl.gz"
TAIL = CAPTURE / "decision-tail.jsonl"
OUTPUT = Path(__file__).with_name("fixtures") / "recall-dungeon-prompt-20261030.json.gz"
STOP_TURN = 479582


def ring_rows(data: bytes) -> list[dict]:
    rows, buf = [], data[data.index(b"\x1f\x8b\x08"):]
    while buf:
        stream = zlib.decompressobj(16 + zlib.MAX_WBITS)
        out = stream.decompress(buf)
        if not stream.eof:
            break  # the ring was copied while its last member was written
        rows.extend(json.loads(line) for line in out.decode("utf-8").splitlines()
                    if line.strip())
        buf = stream.unused_data
    return rows


def main():
    data = RING.read_bytes()
    rows = ring_rows(data)
    board = next(row for row in reversed(rows) if row["type"] == "player_turn")
    assert board["turn"] == STOP_TURN, board["turn"]
    skill = next(row for row in reversed(rows) if row["type"] == "knowledge"
                 and row["knowledge"]["category"] == "skill_exp")
    decisions = []
    for line in TAIL.read_text(encoding="utf-8").splitlines():
        try:
            decisions.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # The bounded tail starts in the middle of a JSON record.
    decision = decisions[-1]
    assert (decision["turn"], decision["reason"], decision["key"]) == (
        STOP_TURN, "emergency:recall", "rc")
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    ids = {row["race_id"] for field in ("visible_monsters", "detected_monsters")
           for row in board.get(field, [])}
    case = dict(
        source="incident-20261030-082816-stuck-prompt (n1-c life-010)",
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (RING, TAIL)},
        board=board,
        skill_knowledge=skill,
        decision={key: decision[key] for key in
                  ("decision_sequence", "turn", "reason", "key", "objective", "messages")},
        monraces={key: asdict(races[key]) for key in sorted(ids)},
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, board["turn"], OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
