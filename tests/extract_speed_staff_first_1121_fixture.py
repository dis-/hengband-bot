"""Extract tests/fixtures/n1b-413-magic-shop-1121/ for test_speed_staff_first_1121_recorded.

Source: the town-arrival checkpoint copied to
C:/hengband-backups/pdca/captures/n1b-413-launcher/n1b413-ta.tgz: n1-b life-413 2026-11-21
23:06:50 (turn 1742125, decision 66613), its first 15 journal rows (row 13 is the Magic shop's
page); the loadout report is left out.

    python tests/extract_speed_staff_first_1121_fixture.py <town-arrival/20261121-230650.769529715-turn1742125>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tests  # noqa: F401,E402 -- isolate live runtime files
from support.town_arrival_fixture import extract  # noqa: E402

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-magic-shop-1121"
ROWS = 15


def main() -> None:
    extract(Path(sys.argv[1]), FIXTURE, ROWS, frozenset({"_loadout_report_path"}))


if __name__ == "__main__":
    main()
