"""Extract tests/fixtures/n1b-419-q33-fire-ants-1126/ (n1b-419-q33-fire-ants-1126).

Source: n1-b life-419's stop of 2026-11-26 08:54:32 (loop-detected on Quest 33, floor (0, 45, 33),
bot main 5175c3635, "confined to [(26, 42)] over 40 decisions"): the rows of life-419's
jsonlog/bot-decisions.jsonl from the session that build started (08:54:05) to the stop, copied to
C:/hengband-backups/pdca/n1b-419-q33-fire-ants/dec.jsonl.

- ``decisions.json.xz``: every decision row of that session (the stop is the last), reduced to what
  the driver's cell loop guard reads (cli._cell_loop_guard_applies, cli._is_looping): the key, the
  reason, the floor, the position, the HP and MP, the board's messages, and the count of hostiles in
  view (the board's ``visible_hostiles``).

    python tests/extract_n1b_419_q33_fire_ants_1126_fixture.py [DECISIONS]
"""
import json
import lzma
import sys
from pathlib import Path

from support.town_arrival_fixture import PRESET

SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "C:/hengband-backups/pdca/n1b-419-q33-fire-ants/dec.jsonl")
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-419-q33-fire-ants-1126"
SESSION_ARGV = "bot-5175c3635"  # the session-start row of the build that stopped


if __name__ == "__main__":
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    start = max(index for index, row in enumerate(rows)
                if row.get("kind") == "session-start" and SESSION_ARGV in " ".join(row.get("argv", [])))
    reduced = [{
        "turn": row.get("turn"), "key": row.get("key"), "reason": row.get("reason"),
        "floor": row.get("floor"), "position": row.get("position"),
        "hp": row["player"].get("hp"), "mp": row["player"].get("mp"),
        "visible_hostiles": row.get("visible_hostiles"),
        "messages": row.get("messages") or [],
    } for row in rows[start + 1:]]
    FIXTURE.mkdir(parents=True, exist_ok=True)
    (FIXTURE / "decisions.json.xz").write_bytes(
        lzma.compress(json.dumps(reduced, ensure_ascii=False).encode("utf-8"), preset=PRESET))
    print(len(reduced), sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
