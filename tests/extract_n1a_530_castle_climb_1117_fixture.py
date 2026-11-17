"""Extract tests/fixtures/n1a-530-castle-climb-1117/.

Source: n1-a life-530's town-arrival checkpoint of 2026-11-17 22:13:09 (turn 10363427,
~/hengbot-soak/n1-a/life-530/jsonlog/town-arrival/20261117-221309.556322800-turn10363427, copied
read-only): the arrival policy, the visit's 12 journal rows (row 11 the Yeek cave mining walk-in
of the no-safe-destination fundraising) and the sidecar files the restored policy reads,
xz-compressed (tests/support/town_arrival_fixture.py).  ``yeek-cave-1f-board.jsonl.gz`` is one
board of the mining run that followed (snapshots-20261117-220327-898599.jsonl.gz, turn 10268566:
the last Yeek cave 1F player_turn with no monster in view), the substrate of the constructed
Castle 49F board.

    python tests/extract_n1a_530_castle_climb_1117_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-castle-climb-1117"
ROWS = 12


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
