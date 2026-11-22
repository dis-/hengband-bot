"""Extract tests/fixtures/n1a-532-home-curse-take-1122/.

Source: n1-a life-532's incident capture of 2026-11-22 14:37:51
(town:blocked:stage-deadline:home, Warrior Lv24, build 53f7a340e), copied read-only from the
viewing server to
C:/hengband-backups/pdca/n1a-532-533/life-532/incident-captures/20261122-143751-town-blocked-stage-deadline-home/.

The fixture keeps the town-arrival checkpoint (``policy.pkl``), the visit's first 29 journal rows
(the arrival through the Alchemist purchase, row 27, and the first step after it, row 28) and the
sidecar files (tests/support/town_arrival_fixture.extract), and
``character-calibration-lv24-heavy-curse.json``: the arrival's calibration sidecar with its pinned
identity set to the worn 耐電のアミュレット after the ``{/f HEAVY_CURSE`` inscription of row 5
(DECLARED CONSTRUCTED: the dump the live bot read after row 6 is not in the checkpoint).

    python tests/extract_n1a_532_home_curse_take_1122_fixture.py
"""
import json
from pathlib import Path

from support.town_arrival_fixture import extract

SOURCE = Path("C:/hengband-backups/pdca/n1a-532-533/life-532/incident-captures/"
              "20261122-143751-town-blocked-stage-deadline-home")
VISIT = SOURCE / "town-arrival"
TARGET = Path(__file__).with_name("fixtures") / "n1a-532-home-curse-take-1122"
ROWS = 29
# The worn amulet's identity after row 5's HEAVY_CURSE inscription (the live bot's _current_pinned_identities).
HEAVY_CURSE_NECK = "d2772517473e53ec"


def main() -> None:
    extract(VISIT, TARGET, ROWS)
    calibration = json.loads((VISIT / "sidecars" / "_character_calibration_path").read_text(encoding="utf-8"))
    calibration["pinned_identities"] = [["neck", HEAVY_CURSE_NECK]]
    (TARGET / "character-calibration-lv24-heavy-curse.json").write_text(
        json.dumps(calibration, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
