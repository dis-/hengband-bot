"""Extract tests/fixtures/n1c-221-me-rod-town-1124/ (tests/test_n1c_221_me_rod_town_1124_recorded.py).

Source: n1-c life-221 (Magic-Eater Lv50), owner halt ``stuck-prompt:ranged:magic-eater-device`` in
town at 2026-11-24 16:56:36 (decision 12404, turn 6454726), a read-only copy in
C:/hengband-backups/pdca/captures/n1c-221-me-rod-town-1124/ of the life's
``incident-captures/20261124-165636-stuck-prompt/town-arrival/``:

  town-arrival/20261124-165613.979637962-turn6454422/
                          the town-arrival checkpoint (decision 12376); row 26 (decision 12403)
                          zapped the absorbed rod ``mCv8`` at the woken 不潔な病人 north of the
                          player, row 27 (decision 12404) walked ``7`` toward the Armoury under
                          the standing ``ranged:magic-eater-device`` and the device compiler
                          refused it at admission (``invalid Magic-Eater device attack``)

Kept: the checkpoint's journal rows up to the refused one (28 rows; the loadout report left out,
as the other town-arrival fixtures).

    python tests/extract_n1c_221_me_rod_town_1124_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1c-221-me-rod-town-1124/town-arrival")
FIXTURE = Path(__file__).with_name("fixtures") / "n1c-221-me-rod-town-1124"
ROWS = 28


def main():
    extract(ROOT / "20261124-165613.979637962-turn6454422", FIXTURE, ROWS,
            frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
