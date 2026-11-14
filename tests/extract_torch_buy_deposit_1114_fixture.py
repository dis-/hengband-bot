"""Extract tests/fixtures/torch-buy-deposit-1114/.

Source: n1-b life-396's incident capture 20261114-110516-town-blocked-stage-deadline-home (the
viewing server's ~/hengbot-soak/n1-b/life-396/jsonlog/incident-captures/, copied read-only to
C:/hengband-backups/pdca/captures/stage-deadline-1114/n1-b/life-396/incident-captures/).  Its
``town-arrival`` checkpoint (20261114-110420, turn 375083) holds the visit that bought one torch
at the General Store and put one in Home 41 times until the stage deadline.

The checkpoint (``policy.pkl``), the visit's first ``ROWS`` journal rows (through the 20-torch
buy, row 62, and the first board outside the General Store, row 65) and the character
calibration the arrival read, xz-compressed.

    python tests/extract_torch_buy_deposit_1114_fixture.py <town-arrival directory>
"""
import gzip
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "torch-buy-deposit-1114"
ROWS = 67
PRESET = 9 | lzma.PRESET_EXTREME


def main(visit: Path) -> None:
    FIXTURE.mkdir(parents=True, exist_ok=True)
    (FIXTURE / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=PRESET))
    rows = gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines(True)
    (FIXTURE / "journal.jsonl.xz").write_bytes(lzma.compress(b"".join(rows[:ROWS]), preset=PRESET))
    (FIXTURE / "calibration.json").write_bytes(
        (visit / "sidecars" / "_character_calibration_path").read_bytes())
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
