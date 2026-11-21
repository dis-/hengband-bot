"""Extract tests/fixtures/n1b-413-launcher-flip-1122/ for test_n1b_413_launcher_flip_1122_recorded.

Sources (n1-b life-413, 2026-11-22): the town-arrival checkpoint of 00:17:35 (turn 2079219,
the next visit after the swap; the swap's own checkpoint had already rotated out), its first
journal row, the loadout report left out; and the *Destruction* staff as the game sent it in the
pack at turn 2051429 (00:13:50, jsonlog/snapshots/snapshots-current.jsonl.gz), kept as
``staff.json``.

    python tests/extract_n1b_413_launcher_flip_1122_fixture.py \
        <town-arrival/20261122-001735.156152928-turn2079219> <snapshots slice .jsonl>
"""
import json
import lzma
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tests  # noqa: F401,E402 -- isolate live runtime files
from support.town_arrival_fixture import PRESET, extract  # noqa: E402

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-launcher-flip-1122"
STAFF_TURN = 2051429


def main() -> None:
    extract(Path(sys.argv[1]), FIXTURE, 1, frozenset({"_loadout_report_path"}))
    for line in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines():
        board = json.loads(line)
        if board["turn"] == STAFF_TURN and board["type"] == "player_turn":
            staff = next(item for item in board["inventory"] if item["name"].startswith("*破壊*"))
            (FIXTURE / "staff.json.xz").write_bytes(lzma.compress(
                json.dumps(staff, ensure_ascii=False).encode("utf-8"), preset=PRESET))
            return
    raise SystemExit("no board at the staff turn")


if __name__ == "__main__":
    main()
