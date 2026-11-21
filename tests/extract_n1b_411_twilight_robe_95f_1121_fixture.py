"""Extract tests/fixtures/n1b-411-twilight-robe-95f-1121/boards.json.xz for
test_n1b_411_twilight_robe_95f_1121_recorded.

Source: n1-b life-411's last 300 state boards on Angband 95F wearing 宵闇のローブ (2026-11-21
12:02-12:03), copied to C:/hengband-backups/pdca/captures/n1b-411-20261121-twilight-robe/
state-tail-1203.jsonl.gz: its first board (turn 11337919, no melee hostile within reach) and its
third (turn 11337924, one within a turn's reach).

    python tests/extract_n1b_411_twilight_robe_95f_1121_fixture.py <capture>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-twilight-robe-95f-1121"


def main() -> None:
    path = Path(sys.argv[1]) / "state-tail-1203.jsonl.gz"
    raws = [json.loads(line) for line in gzip.open(path, "rt", encoding="utf-8")]
    FIXTURE.mkdir(parents=True, exist_ok=True)
    (FIXTURE / "boards.json.xz").write_bytes(lzma.compress(json.dumps(
        {"quiet": raws[0], "closing": raws[2]}, ensure_ascii=False).encode("utf-8"),
        preset=9 | lzma.PRESET_EXTREME))


if __name__ == "__main__":
    main()
