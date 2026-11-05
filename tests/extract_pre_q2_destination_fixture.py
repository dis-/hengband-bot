"""Extract tests/fixtures/pre-q2-destination-1106/ for test_pre_q2_destination_recorded.

Source: C:/hengband-backups/pdca/captures/n1b-318-pre-q2-1106/<visit>, copied read-only
from the viewing server: n1-b life-318's town-arrival visit of 2026-11-06 00:51 up to the
recall read at 00:52:13 ('rgb', town:recall-to-yeek-cave), recompressed with xz.

    python tests/extract_pre_q2_destination_fixture.py <town-arrival visit directory>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

TARGET = Path(__file__).with_name("fixtures") / "pre-q2-destination-1106"
READ_REASON = b'"reason": "town:recall-to-yeek-cave"'
CALIBRATION = "_character_calibration_path"


def main() -> None:
    visit = Path(sys.argv[1])
    preset = 9 | lzma.PRESET_EXTREME
    TARGET.mkdir(parents=True, exist_ok=True)
    (TARGET / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
    rows = gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines(keepends=True)
    last = next(index for index, row in enumerate(rows) if READ_REASON in row)
    assert json.loads(rows[last])["key"] == "rgb"
    (TARGET / "journal.jsonl.xz").write_bytes(
        lzma.compress(b"".join(rows[:last + 1]), preset=preset))
    (TARGET / "calibration.json").write_bytes((visit / "sidecars" / CALIBRATION).read_bytes())


if __name__ == "__main__":
    main()
