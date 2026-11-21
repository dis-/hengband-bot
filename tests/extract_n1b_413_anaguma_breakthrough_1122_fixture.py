"""Extract the fixture of the n1-b life-413 Anaguma break-through of 2026-11-21 (Angband 44F).

Sources, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-413-anaguma-breakthrough-1122:

 - ``state-window.jsonl.gz`` -- the rows of life-413's board stream (jsonlog/snapshots/*.jsonl.gz
   and state.jsonl) with a game turn from 1813700 to 1814000;
 - ``decisions-window.jsonl.gz`` -- the rows of jsonlog/bot-decisions.jsonl* in the same turns.

The life was resumed from an earlier save between 23:25 and 23:27, so the window holds two
histories with the same game turns: Angband 38F (the abandoned one) and 44F (the one that
went on).  The 44F player-turn boards from turn 1813730 to 1813902 (the walk to the start, the
dig, the step out onto the corridor's end and the melt from it) and their decision rows go to
tests/fixtures/n1b-413-anaguma-breakthrough-1122.json.xz.

    python tests/extract_n1b_413_anaguma_breakthrough_1122_fixture.py
"""
import gzip
import json
import lzma
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/n1b-413-anaguma-breakthrough-1122")
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-anaguma-breakthrough-1122.json.xz"
LEVEL = 44
FIRST_TURN, LAST_TURN = 1813730, 1813902
PRESET = 9 | lzma.PRESET_EXTREME


def _rows(name):
    with gzip.open(ROOT / name, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    boards = [row for row in _rows("state-window.jsonl.gz")
              if row.get("type") == "player_turn" and row["floor"]["level"] == LEVEL
              and FIRST_TURN <= row["turn"] <= LAST_TURN]
    decisions = [{"turn": row["turn"], "time": row["time"], "reason": row["reason"],
                  "key": row["key"], "position": row.get("position"), "messages": row.get("messages")}
                 for row in _rows("decisions-window.jsonl.gz")
                 if "reason" in row and row["floor"]["level"] == LEVEL
                 and FIRST_TURN <= row["turn"] <= LAST_TURN]
    fixture = {"boards": boards, "decisions": decisions}
    FIXTURE.write_bytes(lzma.compress(
        json.dumps(fixture, ensure_ascii=False).encode("utf-8", "surrogateescape"), preset=PRESET))
    print("anaguma-breakthrough-413", len(boards), len(decisions))


if __name__ == "__main__":
    main()
