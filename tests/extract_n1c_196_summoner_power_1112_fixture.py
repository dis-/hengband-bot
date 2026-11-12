"""Extract tests/fixtures/n1c-196-summoner-power-1112.json.xz.

Source: the viewing Magic-Eater n1-c life-196 (Lv34, Angband 40F), the stop
captures/20261112-040518-stuck-prompt-summoner-ranged-kill/ copied read-only from the
viewing server to C:/hengband-backups/pdca/captures/me-ranged-stuck-1112/.  The fixture
keeps the last board (turn 2952423, the decision that sent ``mCz@1,39``), the last decision
rows and the stop's screen (control-at-stop.json.gz: the rod list left open under the
power prompt).  ``loop``: n1-b life-373 (Lv9, Yeek cave 3F), the stop
captures/20261112-073011-loop-detected/ copied to the same folder: its last 12 boards
(all turn 800575, 'mBp@14,104' repeated) and their decision rows.

    python tests/extract_n1c_196_summoner_power_1112_fixture.py <capture-dir> <loop-capture-dir>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "n1c-196-summoner-power-1112.json.xz"
TURN = 2952423


def rows(path: Path) -> list:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    root = Path(sys.argv[1])
    board = [raw for raw in rows(root / "state.jsonl.gz") if raw.get("turn") == TURN][-1]
    decisions = [{"turn": row["turn"], "reason": row["reason"], "key": row["key"], "rung": row.get("rung")}
                 for row in rows(root / "bot-decisions.jsonl.gz")][-6:]
    with gzip.open(root / "control-at-stop.json.gz", "rt", encoding="utf-8") as stream:
        stop = json.load(stream)
    loop = Path(sys.argv[2])
    loop_boards = [raw for raw in rows(loop / "state.jsonl.gz") if raw.get("type") == "player_turn"][-12:]
    loop_rows = [{"turn": row["turn"], "reason": row["reason"], "key": row["key"]}
                 for row in rows(loop / "bot-decisions.jsonl.gz")][-6:]
    payload = {"board": board, "decisions": decisions,
               "loop": {"boards": loop_boards, "decisions": loop_rows},
               "stop_screen": {"input_context": stop["screen"]["input_context"],
                               "lines": [line.rstrip() for line in stop["screen"]["lines"][:16]]}}
    OUTPUT.write_bytes(lzma.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                                     .encode("utf-8"), preset=9 | lzma.PRESET_EXTREME))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
