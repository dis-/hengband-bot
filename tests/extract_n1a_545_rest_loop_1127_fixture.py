"""Extract tests/fixtures/n1a-545-rest-loop-1127/ (tests/test_n1a_545_rest_loop_1127_recorded.py).

Source: n1-a life-545 (Amberite Sorcery Rogue CL34 -> CL33; build bot-624020ec7) on hengband.net,
the incident capture ``incident-captures/20261127-143633-loop-detected`` (owner-halt
loop-detected at turn 4963142, Mountain 42F) and the live snapshot generation
``jsonlog/snapshots/snapshots-current.jsonl.gz`` (the capture keeps only its tail), copied
read-only to C:/hengband-backups/pdca/captures/n1a-545-rest-loop-1127/.

Kept: the capture's town-arrival checkpoint (turn 4956323) with its 33 journal rows (the loadout
report left out, as the other town-arrival fixtures), and ``ring.jsonl.xz``: every line of the
snapshot generation after the journal's last board (turn 4957846) through the last board of
``LAST_TURN`` (the responses a board's decision reads, then its ``player_turn`` board), as the CLI
delivered them; ``recorded.json``: the decision log's (turn, key, reason) of those boards
(``jsonlog/bot-decisions.jsonl``, the last row of a turn with a key).

    PYTHONPATH="src;tests;." python tests/extract_n1a_545_rest_loop_1127_fixture.py
"""
import gzip
import json
import lzma
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1a-545-rest-loop-1127")
VISIT = CAPTURE / "20261127-143633-loop-detected" / "town-arrival"
RING = CAPTURE / "snapshots-current-full.jsonl.gz"
DECISIONS = CAPTURE / "bot-decisions.jsonl"
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-rest-loop-1127"
ROWS = 33
JOURNAL_LAST_TURN = 4957846
LAST_TURN = 4960870  # three boards past the first full-HP rest board (4960836)


def ring_lines() -> list[str]:
    kept, pending = [], []
    with gzip.open(RING, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        try:
            for line in stream:
                try:
                    raw = json.loads(line)
                except ValueError:
                    continue
                pending.append(line if line.endswith("\n") else line + "\n")
                if raw.get("type") == "player_turn":
                    turn = raw.get("turn", 0)
                    if JOURNAL_LAST_TURN < turn <= LAST_TURN:
                        kept.extend(pending)
                    pending = []
                    if turn >= LAST_TURN:
                        break
        except (EOFError, OSError):
            pass  # the live generation's unfinished tail
    return kept


def recorded() -> list[list]:
    rows = {}
    with open(DECISIONS, encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            turn = row.get("turn")
            if row.get("key") and turn is not None and JOURNAL_LAST_TURN < turn <= LAST_TURN:
                rows[turn] = [turn, row["key"], row["reason"]]
    return [rows[turn] for turn in sorted(rows)]


def main():
    extract(VISIT, FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    lines = ring_lines()
    (FIXTURE / "ring.jsonl.xz").write_bytes(lzma.compress(
        "".join(lines).encode("utf-8", "surrogateescape"), preset=PRESET))
    (FIXTURE / "recorded.json").write_text(json.dumps(recorded()), encoding="utf-8")
    print(len(lines), sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
