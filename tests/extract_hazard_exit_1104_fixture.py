"""Extract tests/fixtures/hazard-exit-1104.json.gz: n1-a life-478's boards on acid.

Source: C:/hengband-backups/pdca/captures/stops-1104-1330.  Only this tool reads the
capture; the committed test reads the fixture.
"""
from pathlib import Path

from tests.extract_me_staff_loops_1031 import ring_rows
from tests.extract_n1c_loops_0336_1102_fixtures import write


RING = Path("C:/hengband-backups/pdca/captures/stops-1104-1330/n1-a/life-478"
            "/incident-captures/20261104-104549-player-death/snapshots/snapshots-current.jsonl.gz")
TURNS = dict(before_shot=603672, shot=603680, speed_low_hp=603722, rest_deep=602818, heal_deep=602828)


def main() -> None:
    rows = ring_rows(RING)
    write(Path(__file__).with_name("fixtures") / "hazard-exit-1104.json.gz", {
        name: [row for row in rows if row["type"] == "player_turn" and row["turn"] == turn][0]
        for name, turn in TURNS.items()})


if __name__ == "__main__":
    main()
