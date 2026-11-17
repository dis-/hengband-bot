"""Extract tests/fixtures/n1a-530-equip-restore-1118/.

Source: n1-a life-530's incident capture of 2026-11-18 04:57:08
(equipment-transaction:restore-blocked-terminal, bot 130789a3c), copied read-only from hengband.net
~/hengbot-soak/n1-a/life-530/incident-captures/
20261118-045708-equipment-transaction-restore-blocked-terminal/town-arrival/: the arrival checkpoint
(policy.pkl, turn 11690256), all 14 journal rows (row 12 the board the transaction
stopped on) and the sidecar files the restored policy reads, xz-compressed
(tests/support/town_arrival_fixture.py).

    python tests/extract_n1a_530_equip_restore_1118_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-equip-restore-1118"
ROWS = 14


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
