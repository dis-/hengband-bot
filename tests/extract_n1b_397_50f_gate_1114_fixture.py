"""Extract tests/fixtures/n1b-397-50f-gate-1114/.

Source: n1-b life-397's town-arrival checkpoint of 2026-11-14 19:14:06 (turn
4599731, bot 66329f22d), copied read-only from the viewing server's
jsonlog/town-arrival/20261114-191406.340901445-turn4599731/ to
C:/hengband-backups/pdca/n1b-50f-1114/: the arrival policy, the first 84 journal
rows (row 82 the visit's town:character-dump, row 83 the board after it) and the
sidecar files the restored policy reads (the character dump among them; the 12 MB
loadout report is left out), xz-compressed (tests/support/town_arrival_fixture.py).

    python tests/extract_n1b_397_50f_gate_1114_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-397-50f-gate-1114"
ROWS = 84


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
