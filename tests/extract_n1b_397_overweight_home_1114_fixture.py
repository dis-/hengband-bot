"""Extract tests/fixtures/n1b-397-overweight-home-1114/.

Source: n1-b life-397's incident capture 20261114-224042-town-blocked-overweight-
home-unreachable (build e897edf2d), copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-397-overweight-home-1114/: the town-arrival
checkpoint of the 22:40:00 Outpost visit (turn 4638641) and its whole journal
(102 rows, row 101 the board of the stop), the 12 MB loadout report left out; and
the character calibration the visit's row-0 character dump wrote (observed turn
4638641, the same process's session), recorded in the next town-arrival checkpoint
jsonlog/town-arrival/20261114-224048.958791503-turn4639244/.

    PYTHONPATH="src;tests" python tests/extract_n1b_397_overweight_home_1114_fixture.py
"""
import lzma
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1b-397-overweight-home-1114")
VISIT = (CAPTURE / "incident-captures"
         / "20261114-224042-town-blocked-overweight-home-unreachable" / "town-arrival")
DUMPED_CALIBRATION = (CAPTURE / "jsonlog" / "town-arrival"
                      / "20261114-224048.958791503-turn4639244" / "sidecars"
                      / "_character_calibration_path")
TARGET = Path(__file__).with_name("fixtures") / "n1b-397-overweight-home-1114"
ROWS = 102


if __name__ == "__main__":
    extract(VISIT, TARGET, ROWS, frozenset({"_loadout_report_path"}))
    (TARGET / "calibration-after-dump.json.xz").write_bytes(
        lzma.compress(DUMPED_CALIBRATION.read_bytes(), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))
